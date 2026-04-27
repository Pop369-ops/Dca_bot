"""
╔═══════════════════════════════════════════════════════════════════╗
║                       DCA_BOT v1.0                                ║
║       Smart Multi-Exchange Portfolio Manager                     ║
║       Phase 3.1 — Core: Binance + OKX Read-Only + Unified View   ║
║                                                                   ║
║  Features (Phase 3.1):                                            ║
║    💼 Unified portfolio (Binance + OKX)                           ║
║    📊 Real-time balances + USD valuations                         ║
║    💾 Persistent storage (Railway Volume)                         ║
║    🔍 /test command (connectivity check)                          ║
║                                                                   ║
║  Coming in next phases:                                           ║
║    3.2: Trade history sync + auto avg buy price                   ║
║    3.3: Per-coin technical analysis                               ║
║    3.4: Recommendations Engine                                    ║
║    3.5: Sector classification + Alternatives                      ║
║    3.6: DCA Alerts                                                ║
║    3.7: Multi-exchange comparisons + Net Worth tracking           ║
║                                                                   ║
║  للأغراض التعليمية فقط — ليس نصيحة مالية                          ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import hmac
import hashlib
import base64
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlencode

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)


# ══════════════════════════════════════════════════════════════════
# 1. CONFIG
# ══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("DCA_BOT")

# ── Environment Variables ──
BOT_TOKEN          = os.environ.get("BOT_TOKEN", "").strip()

BINANCE_API_KEY    = os.environ.get("BINANCE_API_KEY", "").strip()
BINANCE_SECRET     = os.environ.get("BINANCE_SECRET", "").strip()

OKX_API_KEY        = os.environ.get("OKX_API_KEY", "").strip()
OKX_SECRET         = os.environ.get("OKX_SECRET", "").strip()
OKX_PASSPHRASE     = os.environ.get("OKX_PASSPHRASE", "").strip()

# ── Storage Path (Railway Volume) ──
DATA_DIR = os.environ.get("DATA_DIR", "/data").rstrip("/")
# Fallback to local dir if Railway Volume not mounted (dev/testing)
if not os.path.exists(DATA_DIR) and not os.access("/", os.W_OK):
    DATA_DIR = "./data"

# ── API Endpoints ──
BINANCE_BASE = "https://api.binance.com"
OKX_BASE     = "https://www.okx.com"
CP_BASE      = "https://api.coinpaprika.com/v1"

# ── Filters ──
MIN_USD_VALUE   = 1.0      # ignore dust holdings under $1
SCAN_INTERVAL   = 300      # 5 min

# ── Stablecoins (don't show as positions, just count cash) ──
STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDD",
    "USDP", "GUSD", "PYUSD", "USDE",
}

# ── Timezone ──
TZ_RIYADH = timezone(timedelta(hours=3))


# ══════════════════════════════════════════════════════════════════
# 2. STORAGE LAYER (JSON + Railway Volume)
# ══════════════════════════════════════════════════════════════════

def _ensure_data_dir():
    """Make sure DATA_DIR exists (creates if first run)."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        log.warning(f"[STORAGE] cannot create {DATA_DIR}: {e}")


def storage_load(filename: str, default: Any = None) -> Any:
    """Load JSON file from data dir. Returns default if missing/corrupt."""
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"[STORAGE] failed to load {filename}: {e}")
        return default if default is not None else {}


def storage_save(filename: str, data: Any) -> bool:
    """Save data as JSON to data dir. Atomic write."""
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, filename)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        log.warning(f"[STORAGE] failed to save {filename}: {e}")
        return False


def now_iso() -> str:
    return datetime.now(TZ_RIYADH).isoformat()


def now_str() -> str:
    return datetime.now(TZ_RIYADH).strftime("%H:%M:%S")


# ══════════════════════════════════════════════════════════════════
# 3. HTTP HELPER
# ══════════════════════════════════════════════════════════════════

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; DcaBot/1.0)",
    "Accept": "application/json",
})


def safe_request(method: str, url: str,
                 params: Optional[dict] = None,
                 headers: Optional[dict] = None,
                 timeout: tuple = (5, 20),
                 retries: int = 2) -> Optional[Any]:
    """Resilient HTTP request with retry."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            h = dict(_session.headers)
            if headers:
                h.update(headers)
            r = _session.request(method, url, params=params, headers=h,
                                 timeout=timeout)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return r.text
            elif r.status_code == 429:
                last_err = "429 rate limit"
                time.sleep(2 ** attempt)
                continue
            elif r.status_code in (401, 403):
                return {"_auth_error": r.status_code,
                        "_text": (r.text or "")[:200]}
            else:
                last_err = f"HTTP {r.status_code}: {(r.text or '')[:120]}"
        except requests.exceptions.Timeout:
            last_err = "timeout"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:100]}"
        if attempt < retries:
            time.sleep(1)
    log.warning(f"[HTTP] {method} {url[:70]} → {last_err}")
    return None


# ══════════════════════════════════════════════════════════════════
# 4. BINANCE READ-ONLY CLIENT
# ══════════════════════════════════════════════════════════════════

def binance_signed_request(endpoint: str, params: Optional[dict] = None) -> Optional[Any]:
    """Make a signed Binance API request (HMAC-SHA256)."""
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        return None

    if params is None:
        params = {}

    # Add timestamp + window
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 60000

    # Build query string and sign
    query_string = urlencode(params)
    signature = hmac.new(
        BINANCE_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    params["signature"] = signature

    url = f"{BINANCE_BASE}{endpoint}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}

    return safe_request("GET", url, params=params, headers=headers)


def binance_get_account() -> Optional[Dict]:
    """Get spot account info (balances)."""
    return binance_signed_request("/api/v3/account")


def binance_get_prices() -> Optional[Dict[str, float]]:
    """Get all symbol prices (no auth needed)."""
    data = safe_request("GET", f"{BINANCE_BASE}/api/v3/ticker/price")
    if not isinstance(data, list):
        return None
    return {item["symbol"]: float(item["price"]) for item in data}


def fetch_binance_portfolio() -> Tuple[List[Dict], Optional[str]]:
    """
    Returns (positions, error).
    Each position: {asset, amount, usd_value, source, price_usd}
    """
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        return [], "missing API credentials"

    account = binance_get_account()
    if not account:
        return [], "API request failed (check IP whitelist?)"
    if isinstance(account, dict) and "_auth_error" in account:
        return [], f"auth error {account['_auth_error']}"
    if not isinstance(account, dict) or "balances" not in account:
        return [], "unexpected response"

    prices = binance_get_prices()
    if not prices:
        return [], "could not fetch prices"

    positions = []
    for bal in account.get("balances", []):
        try:
            asset  = bal.get("asset", "")
            free   = float(bal.get("free", 0))
            locked = float(bal.get("locked", 0))
            total  = free + locked
            if total <= 0 or not asset:
                continue

            # Compute USD value
            if asset in STABLECOINS:
                price_usd = 1.0
            else:
                # Try ASSET/USDT first, then ASSET/BUSD, then ASSET/BTC * BTC/USDT
                price_usd = 0
                for quote in ("USDT", "USDC", "BUSD"):
                    sym = f"{asset}{quote}"
                    if sym in prices:
                        price_usd = prices[sym]
                        break

                if price_usd == 0:
                    # Try via BTC pair
                    btc_sym = f"{asset}BTC"
                    btc_usdt = prices.get("BTCUSDT", 0)
                    if btc_sym in prices and btc_usdt > 0:
                        price_usd = prices[btc_sym] * btc_usdt

                if price_usd == 0:
                    continue  # can't price it, skip

            usd_value = total * price_usd
            if usd_value < MIN_USD_VALUE:
                continue  # dust

            positions.append({
                "asset":     asset,
                "amount":    total,
                "free":      free,
                "locked":    locked,
                "price_usd": price_usd,
                "usd_value": usd_value,
                "source":    "binance",
            })
        except (TypeError, ValueError):
            continue

    return positions, None


# ══════════════════════════════════════════════════════════════════
# 5. OKX READ-ONLY CLIENT
# ══════════════════════════════════════════════════════════════════

def _okx_timestamp() -> str:
    """OKX requires ISO 8601 timestamp with milliseconds and 'Z'."""
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _okx_sign(timestamp: str, method: str, path: str, body: str = "") -> str:
    """OKX HMAC-SHA256 signature, base64 encoded."""
    msg = f"{timestamp}{method}{path}{body}"
    sig = hmac.new(
        OKX_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256
    ).digest()
    return base64.b64encode(sig).decode("utf-8")


def okx_signed_request(path: str, params: Optional[dict] = None) -> Optional[Any]:
    """Make a signed OKX API V5 GET request."""
    if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
        return None

    # Build full path with query string
    full_path = path
    if params:
        full_path = f"{path}?{urlencode(params)}"

    timestamp = _okx_timestamp()
    sign = _okx_sign(timestamp, "GET", full_path, "")

    url = f"{OKX_BASE}{full_path}"
    headers = {
        "OK-ACCESS-KEY":        OKX_API_KEY,
        "OK-ACCESS-SIGN":       sign,
        "OK-ACCESS-TIMESTAMP":  timestamp,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type":         "application/json",
    }

    return safe_request("GET", url, headers=headers)


def okx_get_balances() -> Optional[List[Dict]]:
    """Get unified trading account balances + funding account."""
    if not OKX_API_KEY:
        return None

    all_balances = []

    # 1. Trading account (derivatives + spot)
    trading = okx_signed_request("/api/v5/account/balance")
    if trading and isinstance(trading, dict) and trading.get("code") == "0":
        for entry in trading.get("data", []):
            for det in entry.get("details", []):
                try:
                    ccy = det.get("ccy", "")
                    eq = float(det.get("eq", 0) or 0)
                    if ccy and eq > 0:
                        all_balances.append({
                            "ccy":     ccy,
                            "amount":  eq,
                            "account": "trading",
                        })
                except (TypeError, ValueError):
                    continue

    # 2. Funding account (separate from trading on OKX)
    funding = okx_signed_request("/api/v5/asset/balances")
    if funding and isinstance(funding, dict) and funding.get("code") == "0":
        for det in funding.get("data", []):
            try:
                ccy = det.get("ccy", "")
                bal = float(det.get("bal", 0) or 0)
                if ccy and bal > 0:
                    all_balances.append({
                        "ccy":     ccy,
                        "amount":  bal,
                        "account": "funding",
                    })
            except (TypeError, ValueError):
                continue

    return all_balances if all_balances else None


def okx_get_prices() -> Optional[Dict[str, float]]:
    """Get OKX market tickers (no auth)."""
    data = safe_request("GET", f"{OKX_BASE}/api/v5/market/tickers",
                        params={"instType": "SPOT"})
    if not isinstance(data, dict) or data.get("code") != "0":
        return None
    out = {}
    for t in data.get("data", []):
        try:
            inst = t.get("instId", "")
            last = float(t.get("last", 0) or 0)
            if inst and last > 0:
                out[inst] = last
        except (TypeError, ValueError):
            continue
    return out


def fetch_okx_portfolio() -> Tuple[List[Dict], Optional[str]]:
    """Returns (positions, error)."""
    if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
        return [], "missing API credentials (need key + secret + passphrase)"

    balances = okx_get_balances()
    if balances is None:
        # Try ping to get specific error
        test = okx_signed_request("/api/v5/account/balance")
        if isinstance(test, dict):
            if "_auth_error" in test:
                return [], f"auth error {test['_auth_error']} — check passphrase"
            if test.get("code") and test.get("code") != "0":
                return [], f"OKX error: {test.get('msg', 'unknown')}"
        return [], "API request failed"

    prices = okx_get_prices()
    if not prices:
        return [], "could not fetch prices"

    # Aggregate by currency (combine trading + funding)
    aggregated: Dict[str, Dict] = {}
    for b in balances:
        ccy = b["ccy"]
        if ccy not in aggregated:
            aggregated[ccy] = {"amount": 0.0, "accounts": []}
        aggregated[ccy]["amount"] += b["amount"]
        aggregated[ccy]["accounts"].append(b["account"])

    positions = []
    for ccy, info in aggregated.items():
        total = info["amount"]
        if total <= 0:
            continue

        # Price (USD)
        if ccy in STABLECOINS:
            price_usd = 1.0
        else:
            price_usd = 0
            for quote in ("USDT", "USDC", "USD"):
                sym = f"{ccy}-{quote}"
                if sym in prices:
                    price_usd = prices[sym]
                    break
            if price_usd == 0:
                # Try via BTC pair
                btc_sym = f"{ccy}-BTC"
                btc_usdt = prices.get("BTC-USDT", 0)
                if btc_sym in prices and btc_usdt > 0:
                    price_usd = prices[btc_sym] * btc_usdt
            if price_usd == 0:
                continue

        usd_value = total * price_usd
        if usd_value < MIN_USD_VALUE:
            continue

        positions.append({
            "asset":     ccy,
            "amount":    total,
            "price_usd": price_usd,
            "usd_value": usd_value,
            "source":    "okx",
            "accounts":  info["accounts"],
        })

    return positions, None


# ══════════════════════════════════════════════════════════════════
# 6. UNIFIED PORTFOLIO BUILDER
# ══════════════════════════════════════════════════════════════════

def build_unified_portfolio() -> Dict[str, Any]:
    """
    Fetch from both exchanges, merge, return unified view.
    Returns:
    {
      "timestamp": iso,
      "binance":   {"positions": [...], "total_usd": X, "error": ...},
      "okx":       {"positions": [...], "total_usd": Y, "error": ...},
      "unified":   [{asset, total_amount, total_usd, sources: {binance: X, okx: Y}}],
      "total_usd": X + Y,
      "stable_usd": Z,  # cash holdings
      "crypto_usd": Y,  # non-stable holdings
    }
    """
    log.info("[PORTFOLIO] building unified view...")

    binance_positions, binance_err = fetch_binance_portfolio()
    okx_positions, okx_err = fetch_okx_portfolio()

    binance_total = sum(p["usd_value"] for p in binance_positions)
    okx_total     = sum(p["usd_value"] for p in okx_positions)

    # Merge by asset
    by_asset: Dict[str, Dict] = {}
    for p in binance_positions + okx_positions:
        asset = p["asset"]
        if asset not in by_asset:
            by_asset[asset] = {
                "asset":         asset,
                "total_amount":  0.0,
                "total_usd":     0.0,
                "price_usd":     p["price_usd"],
                "sources": {
                    "binance": {"amount": 0.0, "usd": 0.0},
                    "okx":     {"amount": 0.0, "usd": 0.0},
                },
                "is_stable":     asset in STABLECOINS,
            }
        by_asset[asset]["total_amount"] += p["amount"]
        by_asset[asset]["total_usd"]    += p["usd_value"]
        by_asset[asset]["sources"][p["source"]]["amount"] += p["amount"]
        by_asset[asset]["sources"][p["source"]]["usd"]    += p["usd_value"]

    unified = sorted(by_asset.values(), key=lambda x: x["total_usd"], reverse=True)

    stable_usd = sum(a["total_usd"] for a in unified if a["is_stable"])
    crypto_usd = sum(a["total_usd"] for a in unified if not a["is_stable"])
    total_usd  = stable_usd + crypto_usd

    portfolio = {
        "timestamp": now_iso(),
        "binance": {
            "positions": binance_positions,
            "total_usd": binance_total,
            "error":     binance_err,
        },
        "okx": {
            "positions": okx_positions,
            "total_usd": okx_total,
            "error":     okx_err,
        },
        "unified":   unified,
        "total_usd": total_usd,
        "stable_usd": stable_usd,
        "crypto_usd": crypto_usd,
    }

    # Persist snapshot
    storage_save("portfolio_latest.json", portfolio)
    log.info(f"[PORTFOLIO] built. Total: ${total_usd:,.2f}")

    return portfolio


# ══════════════════════════════════════════════════════════════════
# 7. PORTFOLIO FORMATTERS (Telegram output)
# ══════════════════════════════════════════════════════════════════

def _fmt_usd(value: float) -> str:
    """Format USD with appropriate precision."""
    if value >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
    if value >= 1_000:
        return f"${value:,.2f}"
    return f"${value:,.2f}"


def _fmt_amount(amount: float, asset: str = "") -> str:
    """Format crypto amount nicely."""
    if amount >= 1000:
        return f"{amount:,.2f}"
    if amount >= 1:
        return f"{amount:,.4f}"
    if amount >= 0.001:
        return f"{amount:.6f}"
    return f"{amount:.8f}"


def format_unified_portfolio(p: Dict[str, Any]) -> str:
    """Format the unified portfolio as Markdown."""
    lines = []
    lines.append("💼 *محفظتك الموحّدة*")
    lines.append(f"🕐 {now_str()}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # Errors first (if any)
    bin_err = p["binance"].get("error")
    okx_err = p["okx"].get("error")
    if bin_err:
        lines.append(f"⚠️ Binance: `{bin_err}`")
    if okx_err:
        lines.append(f"⚠️ OKX: `{okx_err}`")
    if bin_err or okx_err:
        lines.append("")

    # Top-level totals
    lines.append(f"💰 *الإجمالي*: {_fmt_usd(p['total_usd'])}")
    if p["crypto_usd"] > 0 and p["stable_usd"] > 0:
        crypto_pct = (p["crypto_usd"] / p["total_usd"] * 100) if p["total_usd"] > 0 else 0
        stable_pct = 100 - crypto_pct
        lines.append(f"   📊 Crypto: {_fmt_usd(p['crypto_usd'])} ({crypto_pct:.0f}%)")
        lines.append(f"   💵 Stable: {_fmt_usd(p['stable_usd'])} ({stable_pct:.0f}%)")
    lines.append("")

    # Per-exchange breakdown
    bin_t = p["binance"]["total_usd"]
    okx_t = p["okx"]["total_usd"]
    if bin_t > 0 or okx_t > 0:
        if p["total_usd"] > 0:
            bin_pct = bin_t / p["total_usd"] * 100
            okx_pct = okx_t / p["total_usd"] * 100
        else:
            bin_pct = okx_pct = 0

        lines.append("📍 *التوزيع حسب المنصة:*")
        if bin_t > 0:
            lines.append(f"   Binance: {_fmt_usd(bin_t)} ({bin_pct:.1f}%)")
        if okx_t > 0:
            lines.append(f"   OKX:     {_fmt_usd(okx_t)} ({okx_pct:.1f}%)")
        lines.append("")

    # Per-asset listing
    unified = p["unified"]
    if not unified:
        lines.append("⚪ لا توجد عملات في المحفظة")
        return "\n".join(lines)

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 *العملات ({len(unified)})*:")
    lines.append("")

    for i, asset in enumerate(unified[:20], 1):  # top 20
        sym = asset["asset"]
        total_usd = asset["total_usd"]
        amount = asset["total_amount"]
        price = asset["price_usd"]

        bin_amount = asset["sources"]["binance"]["amount"]
        okx_amount = asset["sources"]["okx"]["amount"]

        # Skip line if total very small after filtering
        if total_usd < MIN_USD_VALUE:
            continue

        # Stable indicator
        if asset["is_stable"]:
            tag = "💵"
        else:
            tag = "🪙"

        amount_str = _fmt_amount(amount, sym)
        lines.append(f"{i}. {tag} *{sym}* — {amount_str} ≈ {_fmt_usd(total_usd)}")

        # Show source split if asset is on both exchanges
        if bin_amount > 0 and okx_amount > 0:
            lines.append(f"   📍 Binance: {_fmt_amount(bin_amount, sym)} | "
                         f"OKX: {_fmt_amount(okx_amount, sym)}")
        elif bin_amount > 0:
            lines.append(f"   📍 Binance")
        elif okx_amount > 0:
            lines.append(f"   📍 OKX")

        # Price (only for non-stable)
        if not asset["is_stable"] and price > 0:
            if price < 0.01:
                price_str = f"${price:.8f}".rstrip('0').rstrip('.')
            elif price < 1:
                price_str = f"${price:.6f}".rstrip('0').rstrip('.')
            else:
                price_str = f"${price:,.4f}"
            lines.append(f"   💰 السعر: `{price_str}`")

    if len(unified) > 20:
        lines.append("")
        lines.append(f"_... و {len(unified) - 20} عملة أخرى (مخفيّة)_")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ _تحليل فقط — لا توصيات بعد (المرحلة 3.3)_")
    lines.append("⚠️ _تنفيذ يدوي 100%_")

    return "\n".join(lines)


def format_single_exchange(p: Dict[str, Any], exchange: str) -> str:
    """Format only one exchange's portfolio."""
    ex_data = p.get(exchange, {})
    positions = ex_data.get("positions", [])
    error = ex_data.get("error")
    total = ex_data.get("total_usd", 0)

    name = "Binance" if exchange == "binance" else "OKX"
    icon = "🟡" if exchange == "binance" else "⚫️"

    lines = []
    lines.append(f"{icon} *محفظة {name}*")
    lines.append(f"🕐 {now_str()}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    if error:
        lines.append(f"❌ *خطأ*: `{error}`")
        lines.append("")
        lines.append("تحقّق من:")
        lines.append("• الـ API keys موجودة في Railway Variables")
        if exchange == "okx":
            lines.append("• الـ Passphrase صحيح")
        lines.append("• الصلاحيات: Read-Only فقط")
        lines.append("• IP Whitelist (لو مفعّل)")
        return "\n".join(lines)

    if not positions:
        lines.append("⚪ لا توجد عملات في هذه المنصة")
        return "\n".join(lines)

    lines.append(f"💰 الإجمالي: {_fmt_usd(total)}")
    lines.append(f"🪙 العملات: {len(positions)}")
    lines.append("")

    sorted_positions = sorted(positions, key=lambda x: x["usd_value"], reverse=True)
    for i, pos in enumerate(sorted_positions[:20], 1):
        asset = pos["asset"]
        amount = pos["amount"]
        usd = pos["usd_value"]
        price = pos["price_usd"]

        tag = "💵" if asset in STABLECOINS else "🪙"
        amount_str = _fmt_amount(amount, asset)
        lines.append(f"{i}. {tag} *{asset}* — {amount_str} ≈ {_fmt_usd(usd)}")

        if asset not in STABLECOINS and price > 0:
            if price < 0.01:
                price_str = f"${price:.8f}".rstrip('0').rstrip('.')
            elif price < 1:
                price_str = f"${price:.6f}".rstrip('0').rstrip('.')
            else:
                price_str = f"${price:,.4f}"
            lines.append(f"   💰 {price_str}")

    if len(sorted_positions) > 20:
        lines.append("")
        lines.append(f"_... و {len(sorted_positions) - 20} عملة أخرى_")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 8. CONNECTIVITY TEST
# ══════════════════════════════════════════════════════════════════

def run_connectivity_test() -> Dict[str, Any]:
    """Test all 3 critical connections: Binance, OKX, CoinPaprika."""
    results = {}

    # Test 1: Binance
    bin_start = time.time()
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        results["binance"] = {
            "ok": False,
            "error": "missing BINANCE_API_KEY or BINANCE_SECRET",
            "elapsed_ms": 0,
        }
    else:
        account = binance_get_account()
        elapsed = int((time.time() - bin_start) * 1000)
        if account and isinstance(account, dict) and "balances" in account:
            non_zero = sum(1 for b in account["balances"]
                          if float(b.get("free", 0)) + float(b.get("locked", 0)) > 0)
            results["binance"] = {
                "ok":      True,
                "balances": non_zero,
                "can_trade": account.get("canTrade", False),
                "permissions": account.get("permissions", []),
                "elapsed_ms": elapsed,
            }
        elif isinstance(account, dict) and "_auth_error" in account:
            results["binance"] = {
                "ok":      False,
                "error":  f"auth error {account['_auth_error']}: {(account.get('_text') or '')[:100]}",
                "elapsed_ms": elapsed,
            }
        else:
            results["binance"] = {
                "ok":      False,
                "error":  "request failed (timeout/network/IP whitelist?)",
                "elapsed_ms": elapsed,
            }

    # Test 2: OKX
    okx_start = time.time()
    if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
        missing = []
        if not OKX_API_KEY:    missing.append("OKX_API_KEY")
        if not OKX_SECRET:     missing.append("OKX_SECRET")
        if not OKX_PASSPHRASE: missing.append("OKX_PASSPHRASE")
        results["okx"] = {
            "ok": False,
            "error": f"missing: {', '.join(missing)}",
            "elapsed_ms": 0,
        }
    else:
        bal = okx_signed_request("/api/v5/account/balance")
        elapsed = int((time.time() - okx_start) * 1000)
        if isinstance(bal, dict) and bal.get("code") == "0":
            details_count = sum(len(e.get("details", [])) for e in bal.get("data", []))
            results["okx"] = {
                "ok":      True,
                "details_count": details_count,
                "elapsed_ms": elapsed,
            }
        elif isinstance(bal, dict) and "_auth_error" in bal:
            results["okx"] = {
                "ok":      False,
                "error":   f"auth error {bal['_auth_error']} — check passphrase",
                "elapsed_ms": elapsed,
            }
        elif isinstance(bal, dict) and bal.get("code") and bal.get("code") != "0":
            results["okx"] = {
                "ok":      False,
                "error":   f"OKX code={bal.get('code')}: {bal.get('msg', '?')}",
                "elapsed_ms": elapsed,
            }
        else:
            results["okx"] = {
                "ok":      False,
                "error":   "request failed",
                "elapsed_ms": elapsed,
            }

    # Test 3: CoinPaprika (price source for non-listed assets)
    cp_start = time.time()
    cp = safe_request("GET", f"{CP_BASE}/global", timeout=(5, 10))
    elapsed = int((time.time() - cp_start) * 1000)
    if cp and isinstance(cp, dict) and "market_cap_usd" in cp:
        results["coinpaprika"] = {
            "ok": True,
            "elapsed_ms": elapsed,
        }
    else:
        results["coinpaprika"] = {
            "ok": False,
            "error": "unreachable",
            "elapsed_ms": elapsed,
        }

    # Test 4: Storage
    storage_ok = storage_save("_health_check.json", {"ts": now_iso()})
    results["storage"] = {
        "ok": storage_ok,
        "path": DATA_DIR,
    }

    return results


# ══════════════════════════════════════════════════════════════════
# 9. TELEGRAM HANDLERS
# ══════════════════════════════════════════════════════════════════

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💼 *DCA_BOT v1.0* — Smart Portfolio Manager\n"
        "_Phase 3.1: Multi-Exchange Read-Only_\n\n"
        "كاشف محفظتك الموحّدة من Binance + OKX، بمنطق احترافي.\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*الميزات الحالية:*\n"
        "💼 محفظة موحّدة (Binance + OKX)\n"
        "📊 أرصدة لحظية + قيم USD\n"
        "💾 حفظ snapshot في Railway Volume\n\n"
        "*الأوامر:*\n"
        "`/start`           القائمة\n"
        "`/test`            فحص الاتصال (Binance + OKX + Storage)\n"
        "`محفظتي`          المحفظة الموحّدة\n"
        "`محفظة Binance`   فقط Binance\n"
        "`محفظة OKX`       فقط OKX\n"
        "`تحديث`            تحديث يدوي\n\n"
        "*الميزات القادمة:*\n"
        "🔜 P&L per coin (3.2)\n"
        "🔜 تحليل فني (3.3)\n"
        "🔜 توصيات Hold/Sell/Buy (3.4)\n"
        "🔜 بدائل ذكية (3.5)\n"
        "🔜 تنبيهات DCA (3.6)\n"
        "🔜 مقارنات + Net Worth tracking (3.7)\n\n"
        "⚠️ _Read-Only — تنفيذ يدوي 100%_\n"
        "⚠️ _تعليمي فقط — ليس نصيحة مالية_"
    )
    await u.message.reply_text(msg, parse_mode="Markdown")


async def cmd_test(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = await u.message.reply_text("⏳ فحص الاتصالات...")

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, run_connectivity_test)

    lines = ["🔍 *نتيجة الفحص:*\n"]

    # Binance
    b = results["binance"]
    if b["ok"]:
        lines.append(f"✅ *Binance*: {b['balances']} عملة | {b['elapsed_ms']}ms")
        perms = b.get("permissions", [])
        if perms:
            lines.append(f"   صلاحيات: `{', '.join(perms)}`")
    else:
        lines.append(f"❌ *Binance*: {b['elapsed_ms']}ms")
        lines.append(f"   _{b.get('error', '?')[:120]}_")

    # OKX
    o = results["okx"]
    if o["ok"]:
        lines.append(f"✅ *OKX*: {o['details_count']} عملة | {o['elapsed_ms']}ms")
    else:
        lines.append(f"❌ *OKX*: {o['elapsed_ms']}ms")
        lines.append(f"   _{o.get('error', '?')[:120]}_")

    # CoinPaprika
    cp = results["coinpaprika"]
    if cp["ok"]:
        lines.append(f"✅ *CoinPaprika*: {cp['elapsed_ms']}ms")
    else:
        lines.append(f"❌ *CoinPaprika*: {cp.get('error', '?')}")

    # Storage
    s = results["storage"]
    icon = "✅" if s["ok"] else "❌"
    lines.append(f"{icon} *Storage*: `{s['path']}`")

    # Summary
    ok_count = sum(1 for k in ("binance", "okx", "coinpaprika", "storage")
                   if results[k]["ok"])
    lines.append("")
    if ok_count == 4:
        lines.append("🎯 *الحالة:* جاهز للاستخدام (4/4)")
    elif ok_count >= 2:
        lines.append(f"⚠️ *الحالة:* جزئي ({ok_count}/4)")
    else:
        lines.append(f"🚨 *الحالة:* غير جاهز ({ok_count}/4)")

    await msg.delete()
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_msg(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text:
        return

    text   = u.message.text.strip()
    text_l = text.lower()

    # ── محفظتي / محفظة ──
    if text_l in ("محفظتي", "محفظة", "portfolio", "wallet"):
        msg = await u.message.reply_text("⏳ جاري قراءة المحفظة من المنصتين...")
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_unified_portfolio)
        formatted = format_unified_portfolio(portfolio)
        await msg.delete()
        await u.message.reply_text(formatted, parse_mode="Markdown")
        return

    # ── محفظة Binance ──
    if "binance" in text_l or text_l in ("محفظة بايننس", "محفظة binance"):
        msg = await u.message.reply_text("⏳ جاري قراءة Binance...")
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_unified_portfolio)
        formatted = format_single_exchange(portfolio, "binance")
        await msg.delete()
        await u.message.reply_text(formatted, parse_mode="Markdown")
        return

    # ── محفظة OKX ──
    if "okx" in text_l or "اوكي" in text or "أوكي" in text:
        msg = await u.message.reply_text("⏳ جاري قراءة OKX...")
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_unified_portfolio)
        formatted = format_single_exchange(portfolio, "okx")
        await msg.delete()
        await u.message.reply_text(formatted, parse_mode="Markdown")
        return

    # ── تحديث ──
    if text_l in ("تحديث", "refresh", "update"):
        msg = await u.message.reply_text("⏳ جاري التحديث...")
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_unified_portfolio)
        await msg.delete()
        await u.message.reply_text(
            f"✅ *تم التحديث*\n\n"
            f"💰 الإجمالي: {_fmt_usd(portfolio['total_usd'])}\n"
            f"🪙 العملات: {len(portfolio['unified'])}\n"
            f"🕐 {now_str()}\n\n"
            f"أرسل `محفظتي` لعرض التفاصيل.",
            parse_mode="Markdown"
        )
        return

    # ── unknown ──
    await u.message.reply_text(
        "🤖 لم أفهم الأمر.\n\nأرسل `/start` لرؤية الأوامر.",
        parse_mode="Markdown"
    )


async def error_handler(update, context):
    log.warning(f"[ERR] {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ خطأ مؤقت. حاول مرة أخرى.")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# 10. MAIN
# ══════════════════════════════════════════════════════════════════

async def _post_init(app):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        log.info("✅ Webhook cleared")
    except Exception as e:
        log.warning(f"webhook clear failed: {e}")


def _print_banner():
    bin_status = "✅ مفعّل" if (BINANCE_API_KEY and BINANCE_SECRET) else "⚪ معطّل"
    okx_status = ("✅ مفعّل"
                  if (OKX_API_KEY and OKX_SECRET and OKX_PASSPHRASE)
                  else "⚪ معطّل")

    print("=" * 70)
    print("  💼 DCA_BOT v1.0 — Smart Portfolio Manager (Phase 3.1) ✅")
    print("=" * 70)
    print(f"  المنصات        :")
    print(f"    🟡 Binance       : {bin_status}")
    print(f"    ⚫️ OKX           : {okx_status}")
    print(f"  Storage         : {DATA_DIR}")
    print(f"  المرحلة          : 3.1 (Core)")
    print(f"  الميزات المتاحة  : محفظة موحّدة + /test")
    print(f"  المرحلة القادمة  : 3.2 (P&L + Avg Buy)")
    print("=" * 70)
    print("  أرسل /start في تيليقرام لبدء الاستخدام")
    print("=" * 70)


def main():
    if not BOT_TOKEN:
        print("=" * 70)
        print("  ❌ ERROR: BOT_TOKEN غير موجود في environment")
        print("  أضفه في Railway → Variables → BOT_TOKEN")
        print("=" * 70)
        return

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_msg
    ))
    app.add_error_handler(error_handler)

    _print_banner()

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
