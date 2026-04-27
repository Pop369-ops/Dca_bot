# 💼 DCA_BOT v1.0 — Smart Multi-Exchange Portfolio Manager

**Phase 3.1**: Unified Portfolio (Binance + OKX) — Read-Only

## 🎯 الهدف

مساعد محفظة شخصي ذكي يقرأ محفظتك من Binance + OKX، يوحّدها في مكان واحد، ويحلّل كل عملة بمنطق احترافي.

## 📡 المصادر

| المصدر | الاستخدام | API Type |
|---|---|---|
| 🟡 **Binance** | محفظة + tickers | Read-Only API |
| ⚫️ **OKX** | محفظة + tickers | Read-Only API + Passphrase |
| 📊 **CoinPaprika** | أسعار احتياطية | مجاني |

## 🔑 Environment Variables

```
BOT_TOKEN              (إلزامي — من BotFather)

BINANCE_API_KEY        (إلزامي — Read-Only)
BINANCE_SECRET         (إلزامي)

OKX_API_KEY            (إلزامي — Read-Only)
OKX_SECRET             (إلزامي)
OKX_PASSPHRASE         (إلزامي — تخترعها أنت)

DATA_DIR=/data         (Railway Volume mount path)
```

## 🌐 Railway Setup

1. Region: `europe-west4` (لتجنب GeoBlocking)
2. Volume: أضف Railway Volume واربطه بـ `/data` (مهم للحفظ المستمر)
3. Variables: أضف الـ 6 مفاتيح أعلاه

## 📝 الأوامر

| الأمر | الوظيفة |
|---|---|
| `/start` | القائمة الرئيسية |
| `/test` | فحص الاتصال (Binance + OKX + Storage) |
| `محفظتي` | المحفظة الموحّدة |
| `محفظة Binance` | فقط Binance |
| `محفظة OKX` | فقط OKX |
| `تحديث` | تحديث يدوي |

## 🛣 Roadmap

- ✅ Phase 3.1: Core (Binance + OKX + Unified Portfolio)
- 🔜 Phase 3.2: Trade history sync + Auto avg buy price
- 🔜 Phase 3.3: Per-coin technical analysis
- 🔜 Phase 3.4: Recommendations Engine (Hold/Sell/Buy/Replace)
- 🔜 Phase 3.5: Sector classification + Alternatives
- 🔜 Phase 3.6: DCA Alerts
- 🔜 Phase 3.7: Multi-exchange comparisons + Net Worth tracking

## ⚠️ Security

- ✅ APIs are **Read-Only** (no trading, no withdrawal)
- ✅ Manual execution only
- ✅ No private keys stored
- ✅ Sensitive vars in Railway Variables (not in code)

## ⚠️ Disclaimer

للأغراض التعليمية فقط — ليس نصيحة مالية.
