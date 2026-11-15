"""Private royalty report file delivery: complete detail, Excel or companion CSV."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import copy
import csv,hashlib,json,os

import pandas as pd
import pyarrow.parquet as pq
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils import get_column_letter
from pandas.io.formats.excel import ExcelFormatter


EXCEL_DATA_ROWS=1_048_575
EXCEL_COLUMNS=16_384


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


from .publication import write_json


@dataclass(frozen=True)
class DetailRows:
    columns: tuple
    count: int
    source: object

    @classmethod
    def from_frame(cls,frame):return cls(tuple(frame.columns),len(frame),frame)

    @classmethod
    def from_parquet(cls,path,headers,expected_rows):
        path=Path(path);f=pq.ParquetFile(path)
        if f.metadata.num_rows!=expected_rows or len(f.schema.names)!=len(headers):
            raise ValueError('El detalle completo no coincide con su control de filas y columnas.')
        return cls(tuple(headers),expected_rows,path)

    def __len__(self):
        return self.count

    @property
    def empty(self):
        return self.count == 0

    @property
    def index(self):
        return range(self.count)

    def rows(self):
        if isinstance(self.source,pd.DataFrame):
            yield from self.source.itertuples(index=False,name=None)
        else:
            f=pq.ParquetFile(self.source)
            for batch in f.iter_batches(batch_size=8192,use_threads=False):
                yield from zip(*(col.to_pylist() for col in batch.columns),strict=True)

    def preview(self):
        from itertools import islice
        return pd.DataFrame(islice(self.rows(),299),columns=self.columns)


def artifact(path,content_type):
    return dict(name=path.name,path=str(path),sha256=sha(path),bytes=path.stat().st_size,content_type=content_type)


def native_template(native,tables,detail,order):
    # The native formatter runs on every summary and exactly the first 300
    # detail rows (including the header) used by its width rule.
    with pd.ExcelWriter(BytesIO(),engine='openpyxl') as writer:
        for name in order:
            frame=detail.preview() if name=='detalle' else tables[name]
            frame.to_excel(writer,index=False,sheet_name=name)
        native.style_workbook(writer)
        theme=tables.get('resumen por tema')
        if theme is not None:
            ws=writer.book['resumen por tema']
            for col,fmt in theme.attrs.get('contract_formats',{}).items():
                for row in ws.iter_rows(min_row=2,min_col=int(col),max_col=int(col)):row[0].number_format=fmt
        book=writer.book
    return book,writer._value_with_fmt


def style_for(cell,prototype,target_styles):
    style=target_styles.get(prototype.style_id)
    if style is None and prototype.has_style:
        sample=WriteOnlyCell(cell.parent)
        for attr in ('font','fill','border','alignment','protection','number_format'):
            setattr(sample,attr,copy(getattr(prototype,attr)))
        style=sample._style;target_styles[prototype.style_id]=style
    cell._style=style
    return cell


def write_xlsx(path,native,tables,detail,order):
    template,value_with_fmt=native_template(native,tables,detail,order)
    output=Workbook(write_only=True);styles={}
    formatter=ExcelFormatter(pd.DataFrame(),na_rep='')
    for original in template.worksheets:
        sheet=output.create_sheet(original.title)
        sheet.freeze_panes=original.freeze_panes
        sheet.sheet_format=copy(original.sheet_format)
        is_detail=original.title=='detalle'
        count=detail.count if is_detail else len(tables[original.title])
        width=len(detail.columns) if is_detail else len(tables[original.title].columns)
        end=f'{get_column_letter(width)}{count+1}' if width else 'A1'
        dimension='A1:'+end if end!='A1' else 'A1'
        sheet.calculate_dimension=lambda dimension=dimension:dimension
        sheet.auto_filter.ref=dimension
        for col,dim in original.column_dimensions.items():sheet.column_dimensions[col].width=dim.width
        for row,dim in original.row_dimensions.items():sheet.row_dimensions[row].height=dim.height
        if not is_detail:
            for row in original.iter_rows():
                cells=[]
                for value in row:
                    cell=style_for(WriteOnlyCell(sheet,value.value),value,styles)
                    if value.hyperlink is not None:cell.hyperlink=copy(value.hyperlink)
                    cells.append(cell)
                sheet.append(cells)
            continue
        sheet.append([style_for(WriteOnlyCell(sheet,c.value),c,styles) for c in original[1]])
        prototype=list(original[2]) if count else []
        written=0
        for row in detail.rows():
            if len(row)!=width:raise ValueError('Una fila de detalle tiene una cantidad de campos incorrecta.')
            cells=[]
            for value,reference in zip(row,prototype,strict=True):
                value,fmt=value_with_fmt(formatter._format_value(value))
                cell=style_for(WriteOnlyCell(sheet,value),reference,styles)
                if fmt and reference.number_format=='General':cell.number_format=fmt
                cells.append(cell)
            sheet.append(cells);written+=1
        if written!=count:raise ValueError('No se escribieron todas las filas del detalle.')
    output.save(path)


def csv_value(value):
    if value is None or pd.isna(value):return ''
    if isinstance(value,float):return repr(float(value))
    return str(value)


def write_csv(path,detail):
    count=0
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(detail.columns)
        for row in detail.rows():
            if len(row)!=len(detail.columns):raise ValueError('Una fila de CSV tiene campos faltantes.')
            writer.writerow(csv_value(v) for v in row);count+=1
    if count!=detail.count:raise ValueError('No se escribieron todas las filas del CSV de detalle.')


def build_files(native,tables,params,output_dir,*,detail=None):
    """Build one complete artifact set. Publish the result only after both files exist."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True,exist_ok=True)
    if 'detalle' in tables:
        if detail is not None:raise ValueError('El detalle fue recibido dos veces.')
        detail=DetailRows.from_frame(tables['detalle'])
    summary={name:frame for name,frame in tables.items() if name!='detalle'}
    if not summary:raise ValueError('Faltan las hojas del resumen.')
    if any(len(frame)>EXCEL_DATA_ROWS or len(frame.columns)>EXCEL_COLUMNS for frame in summary.values()):
        raise ValueError('Una hoja de resumen supera la capacidad de Excel.')
    separate=detail is not None and (detail.count>EXCEL_DATA_ROWS or len(detail.columns)>EXCEL_COLUMNS)
    order=list(tables)
    if separate and 'detalle' in order:order.remove('detalle')
    if detail is not None and not separate and 'detalle' not in order:
        order.insert(order.index('referencias WML') if 'referencias WML' in order else len(order),'detalle')
    excel=native.report_output_path(params['keywords'],params.get('start_month'),params.get('end_month'),output_dir)
    csv_path=excel.with_name(excel.stem+'_detalle.csv') if separate else None
    result_path=output_dir/'result_files.json'
    if result_path.exists() or excel.exists() or (csv_path is not None and csv_path.exists()):
        raise FileExistsError('La carpeta ya tiene archivos de un resultado.')
    with TemporaryDirectory(prefix='generacion_',dir=output_dir) as staging:
        stage=Path(staging)
        write_xlsx(stage/excel.name,native,summary,None if separate else detail,order)
        if csv_path is not None:write_csv(stage/csv_path.name,detail)
        os.replace(stage/excel.name,excel)
        if csv_path is not None:os.replace(stage/csv_path.name,csv_path)
    files=[artifact(excel,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]
    if csv_path is not None:files.append(artifact(csv_path,'text/csv; charset=utf-8'))
    result=dict(files=files,detail_rows=detail.count if detail is not None else 0,
        detail_destination='csv' if separate else 'excel' if detail is not None else 'none',
        excel_data_row_capacity=EXCEL_DATA_ROWS,excel_column_capacity=EXCEL_COLUMNS,
        complete_detail=True,no_row_cutoff=True,download_endpoint_not_exercised=True)
    write_json(result_path, result)
    return result
