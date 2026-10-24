"""Upload only the selected WML inputs; heavy processing always uses Cloud Run."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.load_bigquery_release import load_local_env,storage_client
from app.wml_cloud import stage_inputs,launch_processing

def main():
    load_local_env(ROOT/'.env')
    import os
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--launch',action='store_true')
    parser.add_argument('--input',type=Path,default=ROOT/'input_raw/wml');args=parser.parse_args()
    if not args.apply:raise SystemExit('Usá --apply para preparar exclusivamente los TXT WML seleccionados.')
    bucket=os.environ.get('GCS_BUCKET','vpo-corp-royalties-marts')
    pointer=stage_inputs(args.input,client_factory=storage_client,bucket_name=bucket)
    print(json.dumps(pointer))
    if args.launch:print(json.dumps(launch_processing(client_factory=storage_client,bucket_name=bucket,actor='wml-input-uploader')))

if __name__=='__main__':main()
