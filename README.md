# 💼 DCA_BOT v3.0 — Smart Multi-Exchange Portfolio Manager

**FINAL** — كل الميزات المتفق عليها

## 🎯 الميزات الـ 7

| # | الميزة | الوصف |
|---|---|---|
| 1 | 💼 محفظة موحّدة | Binance + OKX merged |
| 2 | 📊 Auto Avg Buy Price | WAP من trade history |
| 3 | 💰 P&L per coin | Realized + Unrealized |
| 4 | 📈 Technical Analysis | RSI, EMA20/50/200, ATR, Trend |
| 5 | 🎯 Recommendations | Hold/Sell/Buy/Replace/TakeProfit |
| 6 | 🔄 Alternatives Engine | بدائل ذكية لكل عملة ضعيفة |
| 7 | 🔔 DCA Alert Monitor | تنبيهات تلقائية كل 5 دقائق |

## 🆕 الميزات الإضافية في v3.0

- 🆕 **Alternatives Engine** — لما توصية REPLACE، يبحث ويقترح 3 بدائل من نفس القطاع بأعلى momentum
- 🆕 **DCA Alert Monitor** — يراقب محفظتك كل 5 دقائق ويرسل تنبيه عند فرصة DCA / وصول الهدف / Stop Loss
- 🆕 **Net Worth Tracking** — snapshot يومي تلقائي، يعرض تطور المحفظة 30 يوم
- 🆕 **`/analyze SYMBOL`** — تحليل عميق لأي عملة (حتى لو مش في محفظتك)
- 🆕 **`/top`** — أعلى 10 رابحين السوق (لاكتشاف بدائل)
- 🆕 **`/compare BTC`** — مقارنة سعر Binance vs OKX (أرخص أين)
- 🆕 **`/history`** — سجل Net Worth (30 يوم) مع تحليل التغيّر
- 🆕 **`/monitor`** — تفعيل/إيقاف نظام التنبيهات التلقائية

## 🔑 Environment Variables

```
BOT_TOKEN              (إلزامي)
BINANCE_API_KEY        (Read-Only)
BINANCE_SECRET
OKX_API_KEY            (Read-Only)
OKX_SECRET
OKX_PASSPHRASE         (الكلمة اللي اخترعتها)
DATA_DIR=/data         (auto-set)
```

## 🌐 Railway Setup

1. Region: `europe-west4` (إجباري)
2. Volume: mount at `/data`
3. Variables: 6 keys

## 📝 الأوامر الكاملة

### الأوامر الأساسية
| الأمر | الوظيفة |
|---|---|
| `/start` | القائمة الكاملة |
| `/test` | فحص الاتصال |
| `/sync` | force refresh trade history |
| `محفظتي` | التحليل الكامل ⭐ |
| `محفظة Binance` / `محفظة OKX` | منصة واحدة |

### الأوامر الجديدة 🆕
| الأمر | الوظيفة |
|---|---|
| `/analyze BTC` | تحليل عميق لأي عملة |
| `/top` | أعلى 10 رابحين السوق |
| `/compare BTC` | مقارنة Binance vs OKX |
| `/history` | سجل Net Worth (30 يوم) |
| `/monitor` | تشغيل/إيقاف التنبيهات التلقائية |
| `/monitor off` | إيقاف فقط |

## 🔔 أنواع التنبيهات التلقائية

عند تفعيل `/monitor`، البوت يراقب محفظتك كل 5 دقائق ويرسل:

| التنبيه | المنطق |
|---|---|
| 🔔 **فرصة DCA** | السعر هابط 5%+ من avg + RSI < 35 + لا StrongDown |
| 🎯 **وصول الهدف** | السعر وصل ≥ 98% من target |
| ⚠️ **Stop Loss** | السعر وصل ≤ 102% من stop |

**Cooldown**: 6 ساعات لكل تنبيه (لمنع spam)

## 🧠 Recommendation Logic

```
Stable coins                      → HOLD (DCA reserve)
P&L ≥ +50%                        → TAKE_PROFIT_PARTIAL
P&L ≥ +30% AND RSI > 70           → TAKE_PROFIT_PARTIAL
StrongDown AND P&L < -15%         → SELL (cut losses)
P&L < -25% AND Trend Down         → REPLACE → search alternatives
P&L < -8% AND RSI < 35            → BUY_MORE (DCA opportunity)
Trend Up AND RSI < 70             → HOLD (let winners run)
default                           → HOLD (watch)
```

## 🔄 Alternatives Engine Logic

عند توصية REPLACE، البوت:
1. يجلب top 200 من Binance Spot (cached 30 min)
2. يفلتر بنفس قطاع العملة الضعيفة
3. يستبعد العملات الموجودة في محفظتك
4. يحسب momentum score (24h + 7d + RSI + volume)
5. يرشّح الـ3 الأقوى (score ≥ 50)
6. يعرضهم مع تفاصيل لكل واحد

## ⚠️ Disclaimer

- ✅ Read-Only APIs (no trading)
- ✅ Manual execution only
- ⚠️ تعليمي فقط — ليس نصيحة مالية
