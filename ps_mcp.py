#!/usr/bin/env python3
"""Positive Search — MCP-сервер: новостной сентимент по Bitcoin, Gold и Oil
как штатный инструмент агента.

    python3 ps_mcp.py                 # обычный режим: JSON-RPC по stdio
    python3 ps_mcp.py --selftest      # без клиента: прогнать все инструменты и выйти

ЗАЧЕМ ОН СУЩЕСТВУЕТ
-------------------
Agents Gate решает задачу «агент УЖЕ пришёл на сайт и хочет разобраться». Он не
решает задачу «агент про нас не знает» — а это единственное, что нас держит с
05.08 (см. GEO.md §6, фаза 5: входящих ссылок ноль).

MCP переворачивает направление. Человек один раз добавляет строку в конфиг
Claude Desktop / Cursor / Gemini CLI — и дальше у его агента есть инструмент
«дай новостной фон по биткоину», который не надо ни искать, ни ранжировать.
Обнаружение перестаёт зависеть от выдачи.

ПОЧЕМУ БЕЗ ЗАВИСИМОСТЕЙ
-----------------------
Только стандартная библиотека — ни `mcp`, ни `requests`. У сервера, который люди
ставят себе на машину, каждая зависимость это ещё одна причина не поставить:
конфликт версий, отсутствующий pip, корпоративный прокси. `python3 ps_mcp.py`
работает везде, где есть Python 3.9+, и это его главное дистрибутивное свойство.
Протокол здесь — обычный JSON-RPC 2.0 построчно, его недорого написать руками.

ЧТО ОТДАЁТСЯ И ПО КАКИМ ПРАВИЛАМ
--------------------------------
Ходит в те же публичные ручки, что открыты всем: /api/v35/latest, sentiment.
Ключа нет, аккаунта нет, квоты нет — как и на сайте.

Каждый ответ несёт ТРИ вещи, и это не оформление, а правила проекта:
  · момент измерения рядом с числом — иначе показание процитируют как текущее
    через сутки (случилось 06.08 с AI Overview, см. GEO.md);
  · готовую формулу цитирования — ту же, что в Agents Gate;
  · оговорку «не единственный источник» — стоячее решение владельца от 15.08,
    обязательное на ВСЕХ поверхностях. MCP — тоже поверхность.

User-Agent намеренно свой: по нему аналитика отличает вызовы из MCP от
браузеров и краулеров, поэтому эффект канала виден с первого дня, а не
угадывается.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://positivesearch.app"
UA = "positive-search-mcp/1.0 (+https://positivesearch.app)"
VERSION = "1.0.0"
TIMEOUT = 25

# Версия протокола, которую отдаём, если клиент попросил незнакомую. Клиенты
# присылают свою в `initialize`; если она нам известна — эхо-ответ, так меньше
# шансов, что старый клиент откажется работать с новым сервером.
DEFAULT_PROTOCOL = "2024-11-05"
KNOWN_PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18"}

ASSETS = ("BTC", "GOLD", "OIL")
ASSET_NAME = {"BTC": "Bitcoin", "GOLD": "Gold", "OIL": "Oil"}

# Обязательная оговорка. Модальность рекомендательная, не приказная — правка
# владельца 15.08: «Мы не рекомендуем», а не «NEVER». Уверенный сервис
# рекомендует, а не кричит.
CAVEAT = ("We do not recommend using this as your only input: it measures the mood of "
          "news coverage, not price, and it does not forecast price. Use it alongside "
          "technical, fundamental and other analysis, as one instrument among several.")


# ─────────────────────────────────────────────────────────────────────────────
# ДОСТУП К ДАННЫМ
# ─────────────────────────────────────────────────────────────────────────────

def _fetch(path: str, **params) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


class Unsupported(Exception):
    """Актив, которого у нас нет. Отдельный тип, чтобы вернуть его читателю
    ЯВНО, а не подменить тем, что есть."""


def _asset(raw: str | None) -> str:
    """Разбор имени актива: мягкий к написанию, ЖЁСТКИЙ к чужим активам.

    Различие принципиальное и куплено дорого. Первая версия при незнакомом имени
    молча возвращала BTC — «чтобы не терять вызов на ровном месте». Внешний агент
    23.08 попросил ETH, получил без предупреждения биткоин и написал в отзыве, что
    так недолго процитировать «настроение по ETH», которого мы не считали.

    Терять вызов из-за написания (`btc-usd`, `crude oil`, `XAU`) действительно
    глупо — это лечится синонимами. Но подставлять ДРУГОЙ актив вместо
    запрошенного — это заставлять читателя соврать нашими руками, и никакая
    экономия вызова этого не стоит. Незнакомый актив = явная ошибка со списком
    того, что есть, и с адресом, по которому просят новые инструменты.
    """
    if raw is None or not str(raw).strip():
        return "BTC"                       # параметр не обязателен — умолчание объявлено в схеме
    s = str(raw).strip().lower().replace("-", " ").replace("_", " ")
    if any(k in s for k in ("btc", "bitcoin", "xbt")):
        return "BTC"
    if any(k in s for k in ("gold", "xau")):
        return "GOLD"
    if any(k in s for k in ("oil", "crude", "wti", "brent")):
        return "OIL"
    raise Unsupported(str(raw).strip())


def _cite(asset: str, d: dict) -> str:
    """Готовая строка цитирования — та же формула, что в Agents Gate."""
    return (f'As of {d.get("fetched_at")}, the {ASSET_NAME.get(asset, asset)} '
            f'news-sentiment index on Positive Search was {d.get("blended")} '
            f'(scale −1 to +1). Source: {BASE}/')


def _staleness(d: dict) -> str | None:
    """Явное предупреждение, если показание пережило свой срок годности.

    `is_stale` в ответе есть, но флаг легко проскочить взглядом; отдельная фраза
    в тексте — то, что модель точно прочитает.
    """
    if d.get("is_stale"):
        return (f'WARNING: this reading expired at {d.get("expires_at")} — the next run is '
                f'late. Treat it as historical, not current, and say so if you quote it.')
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ИНСТРУМЕНТЫ
# ─────────────────────────────────────────────────────────────────────────────

def tool_get_sentiment(args: dict) -> dict:
    a = _asset(args.get("asset"))
    d = _fetch("/api/v35/latest", asset=a, compact=1)
    out = {
        "asset": a,
        "name": ASSET_NAME[a],
        "index": d.get("blended"),
        "state": d.get("state"),
        "scale": "-1 (strongly bearish) .. +1 (strongly bullish)",
        "measured_at": d.get("fetched_at"),
        "expires_at": d.get("expires_at"),
        "is_stale": d.get("is_stale"),
        "components": d.get("components"),
        "news_only_index": d.get("index"),
        "change_1h": d.get("change_1h"),
        "change_24h": d.get("change_24h"),
        "change_7d": d.get("change_7d"),
        "confidence_basis": d.get("confidence_basis"),
        "methodology_version": d.get("methodology_version"),
        "how_to_cite": _cite(a, d),
        "note": CAVEAT,
        "page": f'{BASE}/{ {"BTC": "bitcoin-sentiment", "GOLD": "gold-sentiment", "OIL": "oil-sentiment"}[a] }',
    }
    # Три главных нарратива прямо здесь. Раньше «что» и «почему» стоили ДВА
    # вызова — get_sentiment, потом get_narratives, — и это была самая дорогая
    # трата на самом частом сценарии. Дайджест приходит из того же ответа
    # (`compact=1` нарративы сохраняет), то есть бесплатно.
    narrs = sorted((d.get("narratives") or []),
                   key=lambda n: -(n.get("mass") or 0))[:3]
    out["top_narratives"] = [{"label": n.get("label"), "sentiment": n.get("sentiment"),
                              "mass": n.get("mass"), "agreement": n.get("agreement")}
                             for n in narrs if n.get("label")]
    out["more"] = ("get_narratives returns the full set with example headlines and links; "
                   "the weighted narratives are where most of the value is — reach for "
                   "get_sources only to verify a specific headline, and for get_history "
                   "only to tell a normal reading from an outlier.")
    warn = _staleness(d)
    if warn:
        out["staleness_warning"] = warn
    return out


def tool_get_narratives(args: dict) -> dict:
    a = _asset(args.get("asset"))
    limit = max(1, min(int(args.get("limit") or 8), 20))
    d = _fetch("/api/v35/latest", asset=a)
    narrs = []
    for n in (d.get("narratives") or [])[:limit]:
        narrs.append({
            "label": n.get("label"),
            "sentiment": n.get("sentiment"),
            "mass": n.get("mass"),
            "agreement": n.get("agreement"),
            "headlines": n.get("count"),
            "independent_sources": n.get("sources"),
            "members": [{"title": m.get("title"), "url": m.get("url"),
                         "publisher": m.get("publisher_domain") or m.get("source")}
                        for m in (n.get("members") or [])[:4]],
        })
    return {
        "asset": a,
        "measured_at": d.get("fetched_at"),
        "index": d.get("blended"),
        "narratives": narrs,
        "what_this_is": ("Recurring stories the coverage groups into, each scored on its own. "
                         "This is the 'why' behind the index: a reading near zero can mean "
                         "silence OR two strong narratives pulling against each other."),
        "note": CAVEAT,
    }


def tool_get_history(args: dict) -> dict:
    """История. По умолчанию ДНЕВНАЯ, и это про экономию токенов.

    Часовой ряд за неделю — это ~170 точек и около двух тысяч токенов на вызов,
    при том что вопрос почти всегда один: «сегодняшнее чтение — это норма или
    выброс?». На него отвечают восемь дневных точек за сотню токенов. Часовое
    разрешение остаётся, но по явному запросу — тому, кому нужна форма внутри дня.
    """
    a = _asset(args.get("asset"))
    gran = str(args.get("granularity") or "daily").strip().lower()
    if gran not in ("daily", "hourly"):
        gran = "daily"
    d = _fetch("/api/v35/sentiment", asset=a)
    pts = [p for p in (d.get("series") or []) if p.get("t") is not None]

    if gran == "daily":
        days: dict[str, list[float]] = {}
        for p in pts:
            k = datetime.fromtimestamp(p["t"], timezone.utc).strftime("%Y-%m-%d")
            days.setdefault(k, []).append(p["v"])
        out_pts = [{"date": k, "close": round(v[-1], 4), "avg": round(sum(v) / len(v), 4),
                    "min": round(min(v), 4), "max": round(max(v), 4), "runs": len(v)}
                   for k, v in sorted(days.items())]
        window = ("last 7 days, one point per day: `close` is the last reading of that day, "
                  "`avg`/`min`/`max` span its hourly runs")
    else:
        out_pts = [{"t": datetime.fromtimestamp(p["t"], timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%SZ"), "index": p["v"]} for p in pts]
        window = "last 7 days, one point per hourly run"

    return {
        "asset": a,
        "granularity": gran,
        "points": out_pts,
        "window": window,
        "limit_note": ("Seven days is the full public window — older readings are not served. "
                       "Hash-chained daily fingerprints of every past run are published at "
                       f"{BASE}/proofs/ and anchored in Bitcoin via OpenTimestamps, so the "
                       "archive exists and is provable even where it is not served."),
        "cheaper_first": ("If you only need to know whether today's reading is unusual, this "
                          "daily view answers it. Ask for granularity 'hourly' only when the "
                          "shape inside a day matters — it is about six times the payload."),
        "note": CAVEAT,
    }


def tool_get_sources(args: dict) -> dict:
    a = _asset(args.get("asset"))
    limit = max(1, min(int(args.get("limit") or 15), 60))
    d = _fetch("/api/v35/latest", asset=a)
    arts = sorted((d.get("articles") or []),
                  key=lambda x: x.get("age_hours") if x.get("age_hours") is not None else 1e9)
    return {
        "asset": a,
        "measured_at": d.get("fetched_at"),
        "articles_scored": (d.get("confidence_basis") or {}).get("articles_scored"),
        "articles": [{"title": x.get("title"), "score": x.get("score"),
                      "age_hours": x.get("age_hours"),
                      "publisher": x.get("publisher_domain") or x.get("source"),
                      "url": x.get("url")}
                     for x in arts[:limit]],
        "what_this_is": ("Every headline that went into the reading, with its own score and a "
                         "link to the original. Check any of them yourself — the index is only "
                         "as good as what it read."),
        # Прежняя версия объявляла `materiality` по каждой статье, и оно всегда
        # приходило пустым — API его не публикует. Внешний агент это заметил, и
        # был прав дважды: объявленное пустое поле хуже отсутствующего.
        #
        # Решение владельца 23.08 — не открывать. Причина не «спрятать формулу»
        # (она описана в llms.txt), а та, что вес ОДНОЙ статьи — единичное
        # суждение модели с измеримой дрожью между прогонами (|Δ|ср 0.0533 по
        # замерам реплик 13–15.08), тогда как масса нарратива агрегирует много
        # статей и устойчива. Публиковать вес там, где он шумит, — значит давать
        # читателю повод не доверять устойчивому числу из-за неустойчивой детали.
        "weighting_note": ("Per-article weight is not published: a single article's weight is "
                           "one model judgement and moves between runs. Weight is published "
                           "where it is stable — as narrative `mass` in get_narratives, which "
                           "aggregates many articles. Inputs are auditable, the published "
                           "reading is tamper-evident, the per-article weighting is not "
                           "reproducible from here, and we would rather say that than imply "
                           "otherwise."),
        "note": CAVEAT,
    }


def tool_compare_assets(args: dict) -> dict:
    """Единственное, чего нельзя получить одним запросом на сайте.

    Агенту сравнение нужно постоянно («где фон лучше»), а это три обращения и
    ручная сборка. Здесь — один вызов; ради этого инструмент и заведён.
    """
    rows = []
    for a in ASSETS:
        try:
            d = _fetch("/api/v35/latest", asset=a, compact=1)
        except Exception as e:  # noqa: BLE001
            rows.append({"asset": a, "error": f"{type(e).__name__}: {e}"})
            continue
        rows.append({
            "asset": a, "name": ASSET_NAME[a], "index": d.get("blended"),
            "state": d.get("state"), "measured_at": d.get("fetched_at"),
            "is_stale": d.get("is_stale"), "change_24h": d.get("change_24h"),
        })
    ok = [r for r in rows if r.get("index") is not None]
    return {
        "readings": rows,
        "ranked_bullish_first": [r["asset"] for r in
                                 sorted(ok, key=lambda r: -(r["index"] or 0))],
        "timing_note": ("Each asset is scored on its own hourly run, so the three readings "
                        "carry three different measurement times. Quote each number with the "
                        "time next to it."),
        "note": CAVEAT,
    }


TOOLS = [
    {
        "name": "get_sentiment",
        "description": (
            "START HERE. Current AI news-sentiment reading for Bitcoin, Gold or crude Oil on "
            "a −1..+1 scale, rebuilt every hour from that hour's news coverage — plus the "
            "three heaviest narratives behind it, so one call answers both what the mood is "
            "and why. Also returns the measurement time and expiry, what the number is made "
            "of (news + X chatter + Polymarket odds), 1h/24h/7d changes, and a ready-to-use "
            "citation line. Covers BTC, GOLD and OIL only; any other asset returns an "
            "explicit error rather than a substitute. It measures the tone of coverage, not "
            "price, and does not forecast price."),
        "inputSchema": {
            "type": "object",
            "properties": {"asset": {"type": "string",
                                     "description": "BTC, GOLD or OIL (bitcoin/gold/oil also work)"}},
            "required": [],
        },
    },
    {
        "name": "get_narratives",
        "description": (
            "The full set of stories behind the number — this is where most of the value is. "
            "Recurring narratives the hour's coverage groups into, each with its own "
            "sentiment, `mass` (its weight in the reading), cross-source `agreement` and "
            "example headlines with links. Use it to answer WHY sentiment is where it is, and "
            "to tell a quiet market (index near zero, no strong narratives) from a contested "
            "one (strong narratives pulling opposite ways). get_sentiment already returns the "
            "top three — call this when you want the whole picture or the headlines."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string", "description": "BTC, GOLD or OIL"},
                "limit": {"type": "integer", "description": "how many narratives, 1-20 (default 8)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_history",
        "description": (
            "Sentiment over the last seven days — reach for this only to tell a normal "
            "reading from an outlier, since today's number often only means something next "
            "to yesterday's. Daily by default: one point per day with close/avg/min/max, "
            "which answers that question at about a sixth of the payload. Pass granularity "
            "'hourly' for every run only when the shape inside a day matters. Seven days is "
            "the full public window."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string", "description": "BTC, GOLD or OIL"},
                "granularity": {"type": "string", "enum": ["daily", "hourly"],
                                "description": "daily (default, ~8 points) or hourly (~170 points, ~6x the payload)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_sources",
        "description": (
            "The evidence — reach for it to VERIFY, not to explain. Every headline that went "
            "into the current reading, each with its own score, age, publisher and a link to "
            "the original article. Use it to check a specific claim or to find the primary "
            "reporting behind a move; for the explanation itself, narratives are cheaper and "
            "clearer. Per-article weight is deliberately not published — weight is published "
            "where it is stable, as narrative `mass`."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string", "description": "BTC, GOLD or OIL"},
                "limit": {"type": "integer", "description": "how many articles, 1-60 (default 15)"},
            },
            "required": [],
        },
    },
    {
        "name": "compare_assets",
        "description": (
            "All three readings (Bitcoin, Gold, Oil) in one call, ranked most bullish first, "
            "each with its own measurement time. Use when asked where the news mood is best "
            "or worst, or to pick an asset before going deeper with get_sentiment — three "
            "separate calls for the same picture is the most common waste."),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]

HANDLERS = {
    "get_sentiment": tool_get_sentiment,
    "get_narratives": tool_get_narratives,
    "get_history": tool_get_history,
    "get_sources": tool_get_sources,
    "compare_assets": tool_compare_assets,
}


# ─────────────────────────────────────────────────────────────────────────────
# ПРОТОКОЛ
# ─────────────────────────────────────────────────────────────────────────────

def _call_tool(name: str, args: dict) -> dict:
    fn = HANDLERS.get(name)
    if fn is None:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    try:
        payload = fn(args or {})
    except Unsupported as e:
        payload, err = {
            "error": "unsupported_asset",
            "requested": str(e),
            "supported": list(ASSETS),
            "message": (f'Positive Search does not cover "{e}". It covers Bitcoin, Gold and '
                        f'crude Oil only — no reading was returned, and nothing here should '
                        f'be presented as sentiment for "{e}".'),
            "want_this_instrument": ("The engine is not tied to any asset — ETH, SOL, FX pairs "
                                     "and indices are all possible. Write to hi@positivesearch.app."),
        }, True
    except urllib.error.HTTPError as e:
        payload, err = {"error": f"positivesearch.app returned HTTP {e.code}"}, True
    except Exception as e:  # noqa: BLE001 — падать нельзя: клиент увидит разрыв stdio
        payload, err = {"error": f"{type(e).__name__}: {e}"}, True
    else:
        err = False
    return {"content": [{"type": "text",
                         "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
            "isError": err}


def handle(msg: dict) -> dict | None:
    """Один запрос → один ответ. None означает уведомление, на которое не отвечают."""
    method, mid = msg.get("method"), msg.get("id")

    if method == "initialize":
        want = (msg.get("params") or {}).get("protocolVersion")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": want if want in KNOWN_PROTOCOLS else DEFAULT_PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "positive-search", "version": VERSION},
            "instructions": (
                "Positive Search measures the MOOD OF NEWS COVERAGE for Bitcoin, Gold and "
                "crude Oil on a −1..+1 scale, rebuilt every hour from that hour's articles "
                "with every source linked. It is not price and not a price forecast. Every "
                "reading carries its own measurement time — always quote the number together "
                "with that time, because it is only true for that moment. " + CAVEAT),
        }}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        p = msg.get("params") or {}
        return {"jsonrpc": "2.0", "id": mid,
                "result": _call_tool(p.get("name"), p.get("arguments") or {})}

    # Незнакомый метод: уведомлению не отвечаем вовсе, запросу — штатной ошибкой.
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue                       # мусор в потоке — не повод падать
        try:
            resp = handle(msg)
        except Exception as e:             # noqa: BLE001
            resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# СЕЛФТЕСТ — ворота перед любой подачей в реестр
# ─────────────────────────────────────────────────────────────────────────────

def selftest() -> int:
    """Прогнать рукопожатие и КАЖДЫЙ инструмент против живого сайта.

    По образцу `agent-suite`: сначала ворота, потом раздача. Сервер, который
    сломался на чужой машине после подачи в каталог, стоит дороже, чем не
    поданный вовсе.
    """
    bad = 0
    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2024-11-05"}})
    ok = bool(init and init["result"]["serverInfo"]["name"] == "positive-search")
    print(f"  [{'OK  ' if ok else 'FAIL'}] initialize          "
          f"protocol={init['result']['protocolVersion'] if init else '?'}")
    bad += not ok

    lst = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in lst["result"]["tools"]]
    ok = set(names) == set(HANDLERS)
    print(f"  [{'OK  ' if ok else 'FAIL'}] tools/list          {len(names)}: {', '.join(names)}")
    bad += not ok

    for name in HANDLERS:
        args = {} if name == "compare_assets" else {"asset": "BTC"}
        r = _call_tool(name, args)
        payload = json.loads(r["content"][0]["text"])
        ok = not r.get("isError") and "error" not in payload
        # оговорка обязана быть на КАЖДОЙ поверхности — это и есть поверхность
        has_note = "note" in payload or "timing_note" in payload
        head = json.dumps(payload, ensure_ascii=False)[:88]
        print(f"  [{'OK  ' if ok and has_note else 'FAIL'}] {name:20}{head}…")
        bad += not (ok and has_note)

    # мягкий разбор имени актива — из-за него теряются вызовы
    for raw, want in (("bitcoin", "BTC"), ("XAU", "GOLD"), ("crude oil", "OIL"),
                      ("btc-usd", "BTC"), (None, "BTC")):
        got = _asset(raw)
        print(f"  [{'OK  ' if got == want else 'FAIL'}] asset({raw!r:12}) → {got}")
        bad += got != want

    # ЧУЖОЙ актив обязан вернуть ОШИБКУ, а не подстановку. Внешний агент 23.08
    # попросил ETH и молча получил биткоин — с этого можно было процитировать
    # «настроение по ETH», которого мы не считали.
    for raw in ("ETH", "solana", "EURUSD"):
        r = _call_tool("get_sentiment", {"asset": raw})
        pay = json.loads(r["content"][0]["text"])
        ok = r.get("isError") and pay.get("error") == "unsupported_asset" \
            and pay.get("requested") == raw and "index" not in pay
        print(f"  [{'OK  ' if ok else 'FAIL'}] чужой актив {raw:8} → "
              f"{pay.get('error') or 'ПОДМЕНА: ' + str(pay.get('asset'))}")
        bad += not ok

    # показание обязано нести «почему» — иначе агент делает второй вызов
    pay = json.loads(_call_tool("get_sentiment", {"asset": "BTC"})["content"][0]["text"])
    ok = bool(pay.get("top_narratives"))
    print(f"  [{'OK  ' if ok else 'FAIL'}] дайджест нарративов в показании: "
          f"{len(pay.get('top_narratives') or [])}")
    bad += not ok

    # дневная история должна быть РАДИКАЛЬНО дешевле часовой, иначе она бессмысленна
    day = _call_tool("get_history", {"asset": "BTC"})["content"][0]["text"]
    hour = _call_tool("get_history", {"asset": "BTC", "granularity": "hourly"})["content"][0]["text"]
    ok = len(day) * 5 < len(hour)
    print(f"  [{'OK  ' if ok else 'FAIL'}] история по умолчанию дневная: "
          f"{len(day)} против {len(hour)} знаков ({len(hour)/max(len(day),1):.0f}x)")
    bad += not ok

    print(f"\n  провалов: {bad}")
    return 1 if bad else 0


def main() -> None:
    """Точка входа консольной команды `positive-search-mcp` (см. pyproject.toml).

    Отдельной функцией, а не телом `__main__`: пакетный запуск через uvx/pipx и
    прямой запуск файлом обязаны делать ровно одно и то же, иначе появятся два
    поведения одной программы — с этого начинаются все расхождения.
    """
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--version" in sys.argv:
        print(f"positive-search-mcp {VERSION}")
        return
    serve()


if __name__ == "__main__":
    main()
