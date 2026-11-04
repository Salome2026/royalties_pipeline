"""Admission regressions: native footers must never hide a broken sale."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ingest_standardized_dashgo as reader
from lib.dashgo_row_classes import CONTROL_LABELS, classify_dashgo_rows
from lib.ingestion_controls import IngestionControlError


HEADER = ['Transaction Date','Store','Region','Artist Name','Label Name','Album Name',
          'Track Artist','UPC','Track Title','VideoId','ChannelId','ISRC','Label Track ID',
          'Composers','Units','Currency','Product Type','Use Type','Revenue','Exchange Rate',
          'USD Revenue','Distribution Rate','Net Revenue','Deal Share','Cover Song',
          'Mechanical Royalty','Pub Admin Fee','Payable','Revenue Split (Y/N)']


def sale(amount='1.25', units='2', title='Same title', isrc='ARABC2600001'):
    values=dict.fromkeys(HEADER,'')
    values.update({'Transaction Date':'2026-01-01','Store':'Youtube AD','Artist Name':'Artist',
                   'Track Title':title,'ISRC':isrc,'Payable':amount,'Units':units})
    return [values[key] for key in HEADER]


def footer():
    control=lambda label: ['']*11+[label,'1.00']
    return [[],control(CONTROL_LABELS[0]),control(CONTROL_LABELS[1]),[],
            control(CONTROL_LABELS[2]),control(CONTROL_LABELS[3]),[],control(CONTROL_LABELS[4])]


class DashGoAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'MAWZ Records-01-27.csv'

    def write(self, records):
        with self.path.open('w',encoding='utf8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(HEADER);writer.writerows(records)
        return reader.read_dashgo_csv(self.path)

    def admitted(self, records):
        frame=self.write(records)
        return reader.standardize_dashgo(frame,self.path)

    def rejected(self, records, code='DASHGO_ROW_STRUCTURE'):
        with self.assertRaises(IngestionControlError) as raised:self.admitted(records)
        self.assertEqual(raised.exception.code,code)

    def test_certified_footer_retains_every_row_and_cell(self):
        records=[sale('1.25'),sale('-0.25'),sale('0')]+footer()
        native=self.write(records);classes=classify_dashgo_rows(native,self.path)
        actual=reader.standardize_dashgo(native,self.path)
        self.assertEqual(actual.height,len(records))
        self.assertEqual(classes.classes,('sale','sale','sale','separator','control','control','separator','control','control','separator','control'))
        self.assertTrue(actual.select(HEADER).equals(native))
        self.assertEqual(actual['amount_usd'].drop_nulls().to_list(),[1.25,-0.25,0.0])

    def test_invalid_sale_amounts_remain_blocked(self):
        for value in ('','not money','NaN','inf','-inf'):
            with self.subTest(value=value):self.rejected([sale(value)]+footer(),'INVALID_AMOUNT')

    def test_blank_full_width_sale_is_not_a_separator(self):
        self.rejected([['']*len(HEADER)]+footer(),'INVALID_AMOUNT')

    def test_short_sale_is_not_discarded(self):self.rejected([['short','1.00']]+footer())

    def test_partial_or_missing_footer_is_blocked(self):
        records=[sale()]+footer()
        for index in range(1,len(records)):
            with self.subTest(missing_record=index):self.rejected(records[:index]+records[index+1:])
        self.rejected([sale()])

    def test_swapped_and_duplicate_control_are_blocked(self):
        records=[sale()]+footer();records[2],records[3]=records[3],records[2]
        self.rejected(records)
        records=[sale()]+footer();records[3]=records[2].copy();self.rejected(records)

    def test_unknown_control_and_extra_context_are_blocked(self):
        records=[sale()]+footer();records[2][11]='Unknown total:';self.rejected(records)
        records=[sale()]+footer();records[2][0]='2026-01-01';self.rejected(records)
        records=[sale()]+footer();records[2].append('extra');self.rejected(records)

    def test_nonfinite_or_missing_control_values_are_blocked(self):
        for value in ('','NaN','inf','-inf','not money'):
            with self.subTest(value=value):
                records=[sale()]+footer();records[-1][-1]=value;self.rejected(records)

    def test_sale_after_footer_is_blocked(self):self.rejected([sale()]+footer()+[sale()])

    def test_control_label_inside_sale_is_blocked(self):
        self.rejected([sale(title=CONTROL_LABELS[0])]+footer())

    def test_prefix_separator_is_retained(self):
        records=[sale(),[],sale()]+footer()
        actual=self.admitted(records);self.assertEqual(actual.height,len(records))

    def test_reordered_frame_is_blocked(self):
        frame=self.write([sale(),sale('2.00')]+footer())
        with self.assertRaises(IngestionControlError):classify_dashgo_rows(frame.reverse(),self.path)

    def test_same_title_with_distinct_identifiers_stays_separate(self):
        actual=self.admitted([sale(isrc='ARABC2600001'),sale(isrc='ARABC2600002'),sale(isrc='')]+footer())
        self.assertEqual(actual['asset_isrc'].head(3).to_list(),['ARABC2600001','ARABC2600002',None])
        self.assertEqual(actual['amount_usd'].head(3).to_list(),[1.25,1.25,1.25])


if __name__=='__main__':unittest.main()
