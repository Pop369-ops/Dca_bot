# 💼 DCA_BOT v2.0 — Smart Multi-Exchange Portfolio Manager

**MVP Bundle** (Phases 3.1 + 3.2 + 3.3 + 3.4)

## 🎯 الميزات

| # | الميزة | الوصف |
|---|---|---|
| 1 | 💼 محفظة موحّدة | Binance + OKX merged |
| 2 | 📊 Auto Avg Buy Price | WAP من trade history |
| 3 | 💰 P&L per coin | Realized + Unrealized |
| 4 | 📈 Technical Analysis | RSI, EMA20/50/200, ATR, Trend |
| 5 | 🎯 Recommendations | Hold/Sell/Buy/Replace/TakeProfit |
| 6 | 🔄 Sector Classification | L1/DeFi/AI/RWA/Meme/Oracle/... |
| 7 | ⚠️ Risk Analysis | Concentration warnings + suggestions |

## 🔑 Environment Variables

```
BOT_TOKEN
BINANCE_API_KEY
BINANCE_SECRET
OKX_API_KEY
OKX_SECRET
OKX_PASSPHRASE
DATA_DIR=/data    (auto-set in code)
```

## 🌐 Railway Setup

1. Region: `europe-west4` (إجباري لـ Binance)
2. Volume: mount at `/data` (للـ trade history persistence)
3. Variables: 6 keys أعلاه

## 📝 الأوامر

| الأمر | الوظيفة |
|---|---|
| `/start` | القائمة الكاملة |
| `/test` | فحص الاتصال |
| `/sync` | force refresh trade history |
| `/bindebug` | تشخيص Binance |
| `محفظتي` | تحليل كامل + توصيات |
| `محفظة Binance` / `محفظة OKX` | منصة واحدة |
| `تحديث` | refresh portfolio |

## 🧠 Recommendation Logic

```
P&L > +30% AND RSI > 70           → TAKE_PROFIT_PARTIAL
P&L > +50%                        → TAKE_PROFIT_PARTIAL
trend StrongDown AND P&L < -15%   → SELL
P&L < -25% AND trend Down         → REPLACE (search alternative in sector)
P&L < -8% AND RSI < 35            → BUY_MORE (DCA opportunity)
trend Up AND RSI < 70             → HOLD (let winners run)
default                           → HOLD (watch)
```

## ⚠️ Disclaimer

- ✅ Read-Only APIs (no trading)
- ✅ Manual execution only
- ⚠️ تعليمي فقط — ليس نصيحة مالية
