# How to build Common

```
git clone https://github.com/Cardinal-Cryptography/common-amm
cd common-amm
make build-and-wrap-all      ## might require cargo-contract 3.2.0, alternatively use make build-and-wrap-all-dockerized
npm run compile
```

# How to start local node with timers

```
cd polkadot-sdk              ## polkadot-sdk fork by Cardinal-Cryptography
git checkout old-timings     ## or wasmi-to-v0.32.0-beta.8
cargo run --profile production --bin substrate-node -- --dev 2> node.log
```

# How to deploy Common

```
cd common-amm
git checkout quick_deploy    ##  this branch reduces number of tokens/pairs deployed
npm run deploy-local         ##  prints, among others, the router address needed below
npm run spawn-dex-data
```

# How to run trades:

Send 50 single-swap trades from Alice (one trade per block):
```
./send_trades.py --common /path/to/common-amm --node-log /path/to/node.log --router [ADDR] --trades 50
```

Please omit `--node-log` if running Substrate version without timers