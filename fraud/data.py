"""Deterministic synthetic card-payments data.

Everything is generated. Card numbers are never stored in full: cards carry a
last-4 and use the 400000 test BIN for display only. Cities are coded metros
(METRO_A ... METRO_L), merchants and people have invented names, and the fraud
labels are synthetic ground truth so the threshold screen can show trade-offs.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

SEED = 4242
AS_OF = dt.date(2026, 11, 10)          # the replay day
DAYS = 30
N_HOLDERS = 2400

METROS = pd.DataFrame({
    "METRO": [f"METRO_{c}" for c in "ABCDEFGHIJKL"],
    "LAT": [40.7, 41.9, 34.1, 29.8, 33.4, 39.7, 47.6, 25.8, 32.8, 42.4, 38.9, 45.5],
    "LON": [-74.0, -87.6, -118.2, -95.4, -112.1, -105.0, -122.3, -80.2, -96.8, -71.1, -77.0, -122.7],
})
CATEGORIES = {  # median amount, card-present share
    "GROCERY": (55, 0.95), "FUEL": (45, 1.0), "RESTAURANT": (38, 0.9), "PHARMACY": (24, 0.85),
    "ENTERTAINMENT": (48, 0.6), "ONLINE_RETAIL": (65, 0.0), "ELECTRONICS": (160, 0.4),
    "TRAVEL": (320, 0.2), "GIFT_CARDS": (50, 0.3),
}
RISKY_MCC = ("ELECTRONICS", "GIFT_CARDS")
FIRST = ["Avery", "Blake", "Casey", "Devon", "Emerson", "Finley", "Harper", "Jordan", "Kendall", "Logan",
         "Morgan", "Parker", "Quinn", "Reese", "Rowan", "Sawyer", "Skyler", "Taylor", "Tatum", "Wren"]
LAST = ["Alder", "Birch", "Calloway", "Dunmore", "Ellison", "Fairbanks", "Garrow", "Hollis", "Ingram", "Jessup",
        "Keating", "Lockhart", "Marlow", "Northcott", "Oakley", "Pemberton", "Quill", "Radford", "Sterling", "Thorne"]
MERCHANT_WORDS = ["Harbor", "Summit", "Cedar", "Beacon", "Granite", "Lumen", "Copper", "Fieldcrest", "Maple", "Juniper"]
MERCHANT_SUFFIX = {"GROCERY": "Market", "FUEL": "Fuel Stop", "RESTAURANT": "Kitchen", "PHARMACY": "Pharmacy",
                   "ENTERTAINMENT": "Cinemas", "ONLINE_RETAIL": "Online Store", "ELECTRONICS": "Electronics",
                   "TRAVEL": "Air & Travel", "GIFT_CARDS": "Gift Card Hub"}

# Named stories for the case screens (card IDs are stable across runs)
PLANTED = {
    "K000101": "Card testing: tiny online charges, then a large purchase",
    "K000202": "Account takeover: new device buying gift cards at night",
    "K000303": "Impossible travel: card-present 3,500 km apart within an hour",
    "K000404": "Legitimate traveler: a late-night purchase after a flight (false positive)",
}
BREACH_MERCHANT = "M0042"   # common point of purchase for a set of compromised cards


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    metros = METROS.copy()

    # Cardholders and cards
    holders = pd.DataFrame({
        "CARDHOLDER_ID": [f"H{n:05d}" for n in range(1, N_HOLDERS + 1)],
        "FIRST_NAME": rng.choice(FIRST, N_HOLDERS), "LAST_NAME": rng.choice(LAST, N_HOLDERS),
        "HOME_METRO": rng.choice(metros.METRO, N_HOLDERS, p=[.16, .12, .12, .09, .07, .07, .07, .07, .07, .06, .05, .05]),
        "SEGMENT": rng.choice(["STANDARD", "REWARDS", "PREMIUM"], N_HOLDERS, p=[.6, .3, .1]),
    })
    holders["EMAIL"] = [f"{f.lower()}.{l.lower()}{i + 1}@example.com" for i, (f, l) in enumerate(zip(holders.FIRST_NAME, holders.LAST_NAME))]
    holders["USUAL_DEVICE"] = [f"DV{n:06d}" for n in range(1, N_HOLDERS + 1)]
    cards = holders[["CARDHOLDER_ID"]].copy()
    second = holders.sample(frac=0.12, random_state=SEED)[["CARDHOLDER_ID"]]
    cards = pd.concat([cards, second], ignore_index=True).sort_values("CARDHOLDER_ID", kind="stable").reset_index(drop=True)
    cards.insert(0, "CARD_ID", [f"K{n:06d}" for n in range(1, len(cards) + 1)])
    cards["LAST4"] = [f"{x:04d}" for x in rng.integers(0, 10000, len(cards))]
    cards["PRODUCT"] = cards.CARDHOLDER_ID.map(dict(zip(holders.CARDHOLDER_ID, holders.SEGMENT)))
    cards["STATUS"] = "ACTIVE"

    # Merchants: every metro has every card-present category; online merchants have no metro
    m_rows = []
    for metro in metros.METRO:
        for cat, (_, cp) in CATEGORIES.items():
            if cp > 0:
                for _ in range(3 if cat in ("GROCERY", "RESTAURANT") else 2):
                    m_rows.append((cat, metro))
    for cat in ("ONLINE_RETAIL", "ELECTRONICS", "TRAVEL", "GIFT_CARDS", "ENTERTAINMENT"):
        for _ in range(8):
            m_rows.append((cat, None))
    merchants = pd.DataFrame(m_rows, columns=["CATEGORY", "METRO"])
    merchants.insert(0, "MERCHANT_ID", [f"M{n:04d}" for n in range(1, len(merchants) + 1)])
    merchants["MERCHANT_NAME"] = [f"{MERCHANT_WORDS[i % 10]} {MERCHANT_SUFFIX[c]}" + ("" if not isinstance(m, str) else f" {m[-1]}")
                                  for i, (c, m) in enumerate(zip(merchants.CATEGORY, merchants.METRO))]
    merchants["CHANNEL"] = np.where(merchants.METRO.isna(), "ONLINE", "CARD_PRESENT")
    merchants.loc[merchants.MERCHANT_ID == BREACH_MERCHANT, ["CATEGORY", "METRO", "CHANNEL"]] = ["FUEL", "METRO_C", "CARD_PRESENT"]
    merchants.loc[merchants.MERCHANT_ID == BREACH_MERCHANT, "MERCHANT_NAME"] = "Granite Fuel Stop C"
    mlat = dict(zip(metros.METRO, metros.LAT)); mlon = dict(zip(metros.METRO, metros.LON))
    cp_by = {k: g.MERCHANT_ID.tolist() for k, g in merchants[merchants.CHANNEL == "CARD_PRESENT"].groupby(["METRO", "CATEGORY"])}
    on_by = {k: g.MERCHANT_ID.tolist() for k, g in merchants[merchants.CHANNEL == "ONLINE"].groupby("CATEGORY")}
    m_metro = {k: v for k, v in zip(merchants.MERCHANT_ID, merchants.METRO)}

    home = dict(zip(holders.CARDHOLDER_ID, holders.HOME_METRO))
    dev = dict(zip(holders.CARDHOLDER_ID, holders.USUAL_DEVICE))
    start = dt.datetime.combine(AS_OF - dt.timedelta(days=DAYS - 1), dt.time(0))
    cats = list(CATEGORIES)

    def txn(card, holder, ts, cat, amount, channel, metro, device, fraud, merchant=None):
        if merchant is None:
            pool = cp_by[(metro, cat)] if channel == "CARD_PRESENT" else on_by.get(cat, on_by["ONLINE_RETAIL"])
            merchant = pool[int(rng.integers(len(pool)))]
        mm = m_metro[merchant]
        lat, lon = (mlat[mm], mlon[mm]) if isinstance(mm, str) else (None, None)
        return {"TS": ts, "CARD_ID": card, "MERCHANT_ID": merchant, "CATEGORY": cat, "AMOUNT": round(float(amount), 2),
                "CHANNEL": channel, "DEVICE_ID": device if channel == "ONLINE" else None,
                "MERCHANT_METRO": mm if channel == "CARD_PRESENT" else None, "LAT": lat, "LON": lon, "IS_FRAUD": fraud}

    rows = []
    travelers = set(rng.choice(holders.CARDHOLDER_ID, int(N_HOLDERS * 0.08), replace=False))
    for c in cards.itertuples():
        h = c.CARDHOLDER_ID
        n = int(rng.poisson(20))
        pref = rng.dirichlet(np.ones(len(cats)) * 1.5)
        trip = None
        if h in travelers:
            d0 = int(rng.integers(2, DAYS - 6))
            dest = rng.choice([m for m in metros.METRO if m != home[h]])
            trip = (d0, d0 + int(rng.integers(2, 4)), dest)
        for _ in range(n):
            day = int(rng.integers(0, DAYS))
            hour = float(rng.choice([rng.uniform(7, 22), rng.uniform(5, 7), rng.uniform(22, 24), rng.uniform(0, 5)], p=[.9, .04, .04, .02]))
            ts = start + dt.timedelta(days=day, hours=hour, seconds=int(rng.integers(0, 60)))
            cat = cats[int(rng.choice(len(cats), p=pref))]
            med, cp = CATEGORIES[cat]
            amount = max(3.0, med * float(np.exp(rng.normal(0, 0.55))))
            channel = "CARD_PRESENT" if rng.random() < cp else "ONLINE"
            metro = home[h]
            if trip and trip[0] <= day <= trip[1]:
                metro = trip[2]
            device = dev[h] if rng.random() > 0.03 else f"DVN{int(rng.integers(100000, 999999))}"   # occasional new phone
            rows.append(txn(c.CARD_ID, h, ts, cat, amount, channel, metro, device, False))
        if trip:  # the flight out, booked the evening before
            rows.append(txn(c.CARD_ID, h, start + dt.timedelta(days=trip[0] - 1, hours=19), "TRAVEL", 340, "ONLINE", home[h], dev[h], False))

    card_holder = dict(zip(cards.CARD_ID, cards.CARDHOLDER_ID))
    replay = dt.datetime.combine(AS_OF, dt.time(0))

    # Background fraud: a few cards per day, with signals of varying strength
    fraud_cards = rng.choice(cards.CARD_ID, 70, replace=False)
    for i, k in enumerate(fraud_cards):
        h = card_holder[k]
        day = int(rng.integers(0, DAYS))
        ts = start + dt.timedelta(days=day, hours=float(rng.uniform(0, 24)))
        style = i % 3
        fdev = f"DVF{i:05d}"
        for j in range(int(rng.integers(1, 4))):
            t = ts + dt.timedelta(minutes=12 * j + int(rng.integers(0, 10)))
            if style == 0:
                rows.append(txn(k, h, t, "ELECTRONICS", rng.uniform(250, 900), "ONLINE", None, fdev, True))
            elif style == 1:
                rows.append(txn(k, h, t, "GIFT_CARDS", rng.uniform(100, 500), "ONLINE", None, fdev, True))
            else:
                far = rng.choice([m for m in metros.METRO if m != home[h]])
                rows.append(txn(k, h, t, rng.choice(["ELECTRONICS", "GROCERY", "FUEL"]), rng.uniform(80, 600), "CARD_PRESENT", far, None, True))

    # Breach: 14 cards used at M0042 between days 18 and 22, then attacked online on the replay day
    breach_cards = [k for k in cards.CARD_ID if home[card_holder[k]] == "METRO_C"][10:24]
    for i, k in enumerate(breach_cards):
        h = card_holder[k]
        rows.append(txn(k, h, start + dt.timedelta(days=18 + i % 5, hours=8 + i % 10), "FUEL", 40 + i, "CARD_PRESENT", "METRO_C", None, False, BREACH_MERCHANT))
        t = replay + dt.timedelta(hours=1 + i * 1.5, minutes=int(rng.integers(0, 50)))
        n = 2 if i % 2 == 0 else 1
        for j in range(n):
            rows.append(txn(k, h, t + dt.timedelta(minutes=9 * j), ["ELECTRONICS", "GIFT_CARDS"][j % 2], 280 + 37 * i, "ONLINE", None, f"DVB{i:04d}", True))

    # Planted stories on the replay day
    def at(hh, mm, ss=0):
        return replay + dt.timedelta(hours=hh, minutes=mm, seconds=ss)
    k = "K000101"; h = card_holder[k]
    for j, (mm, ss, amt) in enumerate([(2, 5, 1.00), (3, 40, 1.49), (5, 2, 0.99), (6, 30, 1.25), (7, 55, 1.10)]):
        rows.append(txn(k, h, at(9, mm, ss), "ONLINE_RETAIL", amt, "ONLINE", None, "DVX00001", True))
    rows.append(txn(k, h, at(9, 10, 40), "ELECTRONICS", 642.00, "ONLINE", None, "DVX00001", True))
    k = "K000202"; h = card_holder[k]
    for mm, amt in [(5, 500.00), (21, 500.00), (34, 450.00)]:
        rows.append(txn(k, h, at(2, mm), "GIFT_CARDS", amt, "ONLINE", None, "DVX00002", True))
    k = "K000303"; h = card_holder[k]
    rows.append(txn(k, h, at(13, 0), "GROCERY", 64.20, "CARD_PRESENT", home[h], None, False))
    hl = (mlat[home[h]], mlon[home[h]])
    far = max(metros.METRO, key=lambda m: (mlat[m] - hl[0]) ** 2 + ((mlon[m] - hl[1]) * 0.8) ** 2)
    rows.append(txn(k, h, at(13, 42), "ELECTRONICS", 918.00, "CARD_PRESENT", far, None, True))
    k = "K000404"; h = card_holder[k]
    dest = "METRO_G" if home[h] != "METRO_G" else "METRO_H"
    rows.append(txn(k, h, at(0, 0) - dt.timedelta(hours=26), "TRAVEL", 410.00, "ONLINE", None, dev[h], False))
    rows.append(txn(k, h, at(1, 12), "ELECTRONICS", 1480.00, "CARD_PRESENT", dest, None, False))

    tx = pd.DataFrame(rows)
    tx["TS"] = pd.to_datetime(tx.TS).dt.floor("s")   # whole seconds, so SQL and Python windows agree exactly
    tx = tx.sort_values(["TS", "CARD_ID"], kind="stable").reset_index(drop=True)
    tx = tx[tx.TS < replay + dt.timedelta(days=1)].reset_index(drop=True)
    tx.insert(0, "TXN_ID", [f"T{n:07d}" for n in range(1, len(tx) + 1)])
    labels = tx[["TXN_ID", "IS_FRAUD"]].copy()
    tx = tx.drop(columns="IS_FRAUD")

    # Profiles: home location, usual device and typical spend, from the customer record
    legit = tx.merge(labels, on="TXN_ID")
    legit = legit[~legit.IS_FRAUD]
    typical = legit.groupby("CARD_ID").AMOUNT.median().round(2)
    prof = cards[["CARD_ID", "CARDHOLDER_ID"]].copy()
    prof["HOME_METRO"] = prof.CARDHOLDER_ID.map(home)
    prof["HOME_LAT"] = prof.HOME_METRO.map(mlat); prof["HOME_LON"] = prof.HOME_METRO.map(mlon)
    prof["USUAL_DEVICE"] = prof.CARDHOLDER_ID.map(dev)
    prof["TYPICAL_AMOUNT"] = prof.CARD_ID.map(typical).fillna(50.0)
    prof = prof.drop(columns="CARDHOLDER_ID")

    # Analyst notes on past confirmed cases (for the patterns screen)
    notes = []
    note_text = {
        True: ["Customer confirmed they did not make the purchase; card reissued.",
               "Online electronics order shipped to a new address; customer denied it.",
               "Gift card purchases from an unrecognized phone; customer was asleep.",
               "Card used in a city the customer has never visited; card was in their wallet."],
        False: ["Customer confirmed the purchase while traveling.",
                "Large purchase confirmed by customer; new laptop.",
                "New phone; customer confirmed the online order."],
    }
    hist = tx.merge(labels, on="TXN_ID")
    hist = hist[pd.to_datetime(hist.TS).dt.date < AS_OF]
    sample = pd.concat([hist[hist.IS_FRAUD].head(60), hist[~hist.IS_FRAUD & (hist.CATEGORY.isin(RISKY_MCC))].head(25)])
    for i, r in enumerate(sample.itertuples()):
        notes.append({"TXN_ID": r.TXN_ID, "NOTE_TS": pd.Timestamp(r.TS) + pd.Timedelta(hours=3),
                      "OUTCOME": "CONFIRMED_FRAUD" if r.IS_FRAUD else "CLEARED",
                      "NOTE": note_text[bool(r.IS_FRAUD)][i % len(note_text[bool(r.IS_FRAUD)])]})

    return {"METROS": metros, "CARDHOLDERS": holders.drop(columns="USUAL_DEVICE"), "CARDS": cards,
            "MERCHANTS": merchants, "CARD_PROFILES": prof, "TRANSACTIONS": tx, "FRAUD_LABELS": labels,
            "ANALYST_NOTES": pd.DataFrame(notes)}
