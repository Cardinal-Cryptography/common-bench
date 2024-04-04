#!/bin/env python

from argparse import ArgumentParser
from os.path import join
from trade import Dex, Trader, check_file

COMMON_DIR = '/home/hansu/aleph/common'

parser = ArgumentParser(prog='send_trades')
parser.add_argument('--router', metavar='AccountId', required=True, help='Router address on chain')
parser.add_argument('--trades', metavar='NUM', type=int, default=10, help='Number of trades to send')
args = parser.parse_args()

metadata_dir = join(COMMON_DIR, 'artifacts')
metadata_files = {
    'router': check_file(metadata_dir, 'router_contract.json'),
    'factory': check_file(metadata_dir, 'factory_contract.json'),
    'pair': check_file(metadata_dir, 'pair_contract.json'),
    'psp22': check_file(metadata_dir, 'psp22.json')
}

chain_url = 'local'
trader_phrase = '//Alice'

dex = Dex(chain_url, args.router, metadata_files, report=True)
dex.fetch_info()

tr = Trader(dex, trader_phrase)
tr.update_balances()
tr.set_allowances()

for _ in range(args.trades):
    tr.trade(1)
