"""
NEXUS TOPUP - Website top up game bertema gaming (Flask, satu file).

Cara menjalankan:
    pip install flask
    python app.py
Lalu buka http://127.0.0.1:5000

Catatan: ini versi demo. Pesanan disimpan di memori (hilang saat server restart)
dan pembayaran hanya simulasi. Untuk produksi, sambungkan ke payment gateway
(Midtrans/Xendit/Tripay) dan API supplier top up, lalu ganti ORDERS dengan database.
"""
import os
import re
import time
import uuid

from flask import Flask, abort, jsonify, render_template, request
from jinja2 import DictLoader

app = Flask(__name__)

# ----------------------------------------------------------------------------
# DATA
# ----------------------------------------------------------------------------
GAMES = {
    "mobile-legends": {
        "name": "Mobile Legends", "short": "ML", "color": "#4d7cff", "color2": "#8a3ffc",
        "currency": "Diamond", "tag": "MOBA 5v5",
        "desc": "Top up Diamond Mobile Legends: Bang Bang. Masukkan User ID dan Zone ID.",
        "fields": [
            {"name": "user_id", "label": "User ID", "ph": "Contoh: 12345678", "re": r"^\d{5,12}$",
             "err": "User ID berisi 5-12 angka."},
            {"name": "zone_id", "label": "Zone ID", "ph": "Contoh: 1234", "re": r"^\d{3,6}$",
             "err": "Zone ID berisi 3-6 angka."},
        ],
        "packages": [(5, 1500), (12, 3500), (28, 8000), (59, 16500), (172, 47000), (344, 93000),
                     (706, 187000)],
    },
    "free-fire": {
        "name": "Free Fire", "short": "FF", "color": "#ff7a18", "color2": "#ff2d55",
        "currency": "Diamond", "tag": "Battle Royale",
        "desc": "Top up Diamond Free Fire langsung ke akunmu lewat Player ID.",
        "fields": [
            {"name": "user_id", "label": "Player ID", "ph": "Contoh: 123456789", "re": r"^\d{6,12}$",
             "err": "Player ID berisi 6-12 angka."},
        ],
        "packages": [(5, 800), (12, 1900), (50, 7000), (140, 19000), (355, 47000), (720, 94000),
                     (1450, 188000)],
    },
    "pubg-mobile": {
        "name": "PUBG Mobile", "short": "PUBG", "color": "#f5b301", "color2": "#c77d00",
        "currency": "UC", "tag": "Battle Royale",
        "desc": "Top up UC PUBG Mobile (Global) cukup dengan Character ID.",
        "fields": [
            {"name": "user_id", "label": "Character ID", "ph": "Contoh: 5123456789", "re": r"^\d{6,14}$",
             "err": "Character ID berisi 6-14 angka."},
        ],
        "packages": [(60, 15000), (325, 75000), (660, 150000), (1800, 375000), (3850, 750000),
                     (8100, 1500000)],
    },
    "roblox": {
        "name": "Roblox", "short": "RBX", "color": "#00c2ff", "color2": "#0077ff",
        "currency": "Robux", "tag": "Sandbox",
        "desc": "Beli Robux untuk avatar, item, dan game favoritmu. Cukup username Roblox.",
        "fields": [
            {"name": "user_id", "label": "Username Roblox", "ph": "Contoh: NexusPlayer_01",
             "re": r"^[A-Za-z0-9_]{3,20}$", "err": "Username 3-20 karakter (huruf, angka, garis bawah)."},
        ],
        "packages": [(80, 15000), (400, 75000), (800, 150000), (1700, 300000), (4500, 750000),
                     (10000, 1500000)],
    },
    "efootball": {
        "name": "eFootball", "short": "eF", "color": "#18d67c", "color2": "#0a8f6a",
        "currency": "eFootball Coins", "tag": "Sepak Bola",
        "desc": "Top up eFootball Coins untuk Pack, pemain, dan event. Pakai Konami ID.",
        "fields": [
            {"name": "user_id", "label": "Konami ID / User ID", "ph": "Contoh: A1B2C3D4E",
             "re": r"^[A-Za-z0-9]{6,16}$", "err": "ID berisi 6-16 huruf/angka."},
        ],
        "packages": [(130, 23000), (300, 52000), (550, 95000), (1040, 175000), (2130, 350000),
                     (3250, 525000)],
    },
}

PAYMENTS = {
    "qris":    {"name": "QRIS", "note": "Semua e-wallet & m-banking", "pct": 0.7, "flat": 0},
    "gopay":   {"name": "GoPay", "note": "Instan", "pct": 2.0, "flat": 0},
    "dana":    {"name": "DANA", "note": "Instan", "pct": 1.5, "flat": 0},
    "shopee":  {"name": "ShopeePay", "note": "Instan", "pct": 1.8, "flat": 0},
    "bca":     {"name": "Transfer BCA", "note": "Virtual Account", "pct": 0, "flat": 2500},
    "alfamart": {"name": "Alfamart", "note": "Bayar di kasir", "pct": 0, "flat": 3500},
}

ORDERS = {}  # order_id -> dict


def rupiah(n):
    return "Rp " + f"{int(n):,}".replace(",", ".")


def game_view(slug):
    """Bentuk data game yang aman dikirim ke template/JS."""
    g = GAMES[slug]
    pk = [{"id": i, "amount": a, "price": p} for i, (a, p) in enumerate(g["packages"])]
    return {**g, "slug": slug, "pk": pk}


app.jinja_env.filters["rp"] = rupiah


def game_img(slug):
    """Cari gambar game di static/img/<slug>.(jpg|jpeg|png|webp). None jika belum ada."""
    for ext in ("jpg", "jpeg", "png", "webp"):
        if os.path.exists(os.path.join(app.static_folder, "img", f"{slug}.{ext}")):
            return f"/static/img/{slug}.{ext}"
    return None


app.jinja_env.globals["game_img"] = game_img

# ----------------------------------------------------------------------------
# TEMPLATE
# ----------------------------------------------------------------------------
BASE = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{% block title %}RAFFZ TOPUP{% endblock %}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#07060f;--panel:#12101f;--panel2:#191530;--line:#2b2650;--text:#ece9ff;--muted:#9a95c4;
--neon:#7c5cff;--cyan:#22e4ff;--pink:#ff3df2;--ok:#2cff9a;--bad:#ff4d6d;color-scheme:dark;
--head:'Orbitron',system-ui,sans-serif;--body:'Rajdhani',system-ui,sans-serif}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:600 18px/1.45 var(--body);
background-image:radial-gradient(900px 500px at 85% -10%,#3a1d8a55,transparent),
radial-gradient(700px 500px at -10% 30%,#00a9ff22,transparent);padding-bottom:env(safe-area-inset-bottom,0)}
a{color:inherit;text-decoration:none}
.wrap{width:min(1120px,100% - 32px);margin-inline:auto}
header{position:sticky;top:0;z-index:20;backdrop-filter:blur(14px);background:#07060fcc;
border-bottom:1px solid var(--line);padding-top:env(safe-area-inset-top,0)}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:64px}
.logo{font:900 22px var(--head);letter-spacing:1px}
.logo b{color:var(--cyan);text-shadow:0 0 14px var(--cyan)}
nav{display:flex;gap:22px;color:var(--muted)}
nav a:hover{color:var(--text)}
.btn{display:inline-block;border:0;cursor:pointer;font:800 16px var(--head);letter-spacing:.5px;color:#fff;
padding:14px 26px;border-radius:10px;background:linear-gradient(90deg,var(--neon),var(--pink));
box-shadow:0 0 24px #7c5cff77;transition:transform .15s,box-shadow .15s}
.btn:hover{transform:translateY(-2px);box-shadow:0 0 36px #ff3df277}
.btn.ghost{background:transparent;border:1px solid var(--line);box-shadow:none}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
:focus-visible{outline:2px solid var(--cyan);outline-offset:3px}

/* HERO */
.hero{position:relative;padding:84px 0 70px;overflow:hidden}
.hero::before{content:"";position:absolute;inset:0;background:
linear-gradient(var(--line) 1px,transparent 1px) 0 0/56px 56px,
linear-gradient(90deg,var(--line) 1px,transparent 1px) 0 0/56px 56px;
mask-image:radial-gradient(ellipse at 50% 30%,#000 10%,transparent 70%);opacity:.55;animation:grid 14s linear infinite}
@keyframes grid{to{background-position:0 56px,56px 0}}
.hero .wrap{position:relative}
h1{font:900 clamp(34px,6.4vw,76px)/1.05 var(--head);margin:0 0 18px;letter-spacing:-1px;max-width:15ch}
h1 span{background:linear-gradient(90deg,var(--cyan),var(--pink));-webkit-background-clip:text;background-clip:text;color:transparent;
filter:drop-shadow(0 0 18px #7c5cff88)}
.hero p{color:var(--muted);font-size:21px;max-width:52ch;margin:0 0 30px}
.stats{display:flex;gap:34px;margin-top:44px;flex-wrap:wrap}
.stats div{border-left:3px solid var(--neon);padding-left:14px}
.stats b{display:block;font:800 26px var(--head)}
.stats small{color:var(--muted);font-size:16px}

/* GAME CARDS */
h2{font:800 clamp(22px,3vw,32px) var(--head);margin:0 0 26px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:20px}
.card{--c:#7c5cff;--c2:#ff3df2;position:relative;display:block;border-radius:16px;padding:22px;background:var(--panel);
border:1px solid var(--line);overflow:hidden;transition:transform .2s,border-color .2s,box-shadow .2s}
.card::after{content:"";position:absolute;inset:auto -30% -60% -30%;height:80%;background:radial-gradient(closest-side,var(--c),transparent);opacity:.18;transition:opacity .2s}
.card:hover{transform:translateY(-6px);border-color:var(--c);box-shadow:0 12px 40px -12px var(--c)}
.card:hover::after{opacity:.4}
.emblem{width:76px;height:76px;border-radius:18px;display:grid;place-items:center;font:900 22px var(--head);color:#fff;
background:linear-gradient(135deg,var(--c),var(--c2));box-shadow:0 0 26px -4px var(--c);margin-bottom:16px;text-shadow:0 2px 8px #0008}
.cover{display:block;width:100%;aspect-ratio:1;object-fit:cover;border-radius:14px;margin-bottom:16px;
border:1px solid var(--c);box-shadow:0 0 28px -6px var(--c);transition:transform .25s}
.card:hover .cover{transform:scale(1.03)}
.cover.sm{width:104px;margin:0;flex:none;aspect-ratio:1}
.card h3{font:800 20px var(--head);margin:0 0 4px}
.card small{color:var(--muted)}
.pill{position:absolute;top:16px;right:16px;font-size:14px;padding:3px 10px;border-radius:99px;border:1px solid var(--c);color:var(--c)}
.go{display:block;margin-top:14px;color:var(--c);font:800 15px var(--head)}
section{padding:46px 0}
.feat{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}
.feat div{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px}
.feat h4{margin:0 0 6px;font:800 17px var(--head);color:var(--cyan)}
.feat p{margin:0;color:var(--muted)}
footer{border-top:1px solid var(--line);padding:30px 0 40px;color:var(--muted);text-align:center;margin-top:40px}

/* TOPUP PAGE */
.top{display:grid;grid-template-columns:1fr 340px;gap:26px;align-items:start;padding:36px 0 20px}
.banner{--c:#7c5cff;--c2:#ff3df2;display:flex;gap:20px;align-items:center;padding:24px;border-radius:16px;margin-top:30px;
background:linear-gradient(120deg,var(--panel2),var(--panel));border:1px solid var(--line);border-left:4px solid var(--c)}
.banner .emblem{margin:0;flex:none}
.banner h1{font-size:clamp(24px,4vw,38px);margin:0 0 4px}
.banner p{margin:0;color:var(--muted)}
.box{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px;margin-bottom:20px}
.box h3{font:800 18px var(--head);margin:0 0 16px;display:flex;align-items:center;gap:12px}
.box h3 i{font-style:normal;display:grid;place-items:center;width:30px;height:30px;border-radius:8px;background:var(--neon);font-size:15px}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
label.f span{display:block;color:var(--muted);margin-bottom:6px;font-size:16px}
input[type=text]{width:100%;background:#0b0916;border:1px solid var(--line);border-radius:10px;padding:13px 14px;color:var(--text);font:600 18px var(--body)}
input[type=text]:focus{outline:none;border-color:var(--cyan);box-shadow:0 0 0 3px #22e4ff22}
input.bad{border-color:var(--bad)}
.err{color:var(--bad);font-size:15px;min-height:18px;margin-top:4px}
.opts{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.opt{position:relative;cursor:pointer}
.opt input{position:absolute;opacity:0;inset:0}
.opt div{height:100%;border:1px solid var(--line);background:var(--panel2);border-radius:12px;padding:14px;transition:.15s}
.opt:hover div{border-color:var(--muted)}
.opt input:checked+div{border-color:var(--c);background:linear-gradient(160deg,#ffffff0d,transparent);box-shadow:0 0 22px -6px var(--c),inset 0 0 0 1px var(--c)}
.opt input:focus-visible+div{outline:2px solid var(--cyan);outline-offset:2px}
.opt b{display:block;font:800 17px var(--head)}
.opt small{color:var(--muted);font-size:15px}
.opt em{display:block;font-style:normal;color:var(--ok);margin-top:6px;font-weight:700}
.sum{position:sticky;top:84px}
.sum dl{margin:0;display:grid;grid-template-columns:1fr auto;gap:8px 12px}
.sum dt{color:var(--muted)}.sum dd{margin:0;text-align:right}
.sum hr{border:0;border-top:1px dashed var(--line);margin:14px 0}
.total{font:900 26px var(--head);color:var(--cyan);text-shadow:0 0 16px #22e4ff55}
.sum .btn{width:100%;margin-top:16px}
.invoice{max-width:620px;margin:50px auto}
.status{display:inline-block;padding:4px 14px;border-radius:99px;font-weight:700}
.st-pending{background:#ffb70022;color:#ffb700;border:1px solid #ffb700}
.st-success{background:#2cff9a22;color:var(--ok);border:1px solid var(--ok)}
.row{display:flex;justify-content:space-between;gap:16px;padding:9px 0;border-bottom:1px dashed var(--line)}
.row span:first-child{color:var(--muted)}
@media (max-width:860px){.top{grid-template-columns:1fr}.sum{position:static}nav{display:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<header><div class="wrap">
  <a class="logo" href="/">RAFFZ<b>GAME</b></a>
  <nav><a href="/#games">Game</a><a href="/#why">Keunggulan</a></nav>
  <a class="btn" style="padding:10px 18px;font-size:14px" href="/#games">Top up</a>
</div></header>
{% block body %}{% endblock %}
<footer><div class="wrap">© 2026 RAFFZ GAME. Situs demo; semua merek dagang milik pemilik masing-masing.</div></footer>
</body></html>"""

HOME = r"""{% extends "base.html" %}
{% block body %}
<div class="hero"><div class="wrap">
  <h1>Top up game, <span>naik level</span> tanpa nunggu.</h1>
  <p>Pilih game, masukkan ID, bayar. Item masuk ke akunmu dalam hitungan detik, 24 jam setiap hari.</p>
  <a class="btn" href="#games">Mulai top up</a>
  <div class="stats">
    <div><b>&lt; 10 dtk</b><small>Rata-rata proses</small></div>
    <div><b>24/7</b><small>Layanan otomatis</small></div>
    <div><b>6</b><small>Metode pembayaran</small></div>
  </div>
</div></div>

<section id="games"><div class="wrap">
  <h2>Pilih game kamu</h2>
  <div class="grid">
  {% for slug, g in games.items() %}
    <a class="card" href="/game/{{ slug }}" style="--c:{{ g.color }};--c2:{{ g.color2 }}">
      <span class="pill">{{ g.tag }}</span>
      {% set im = game_img(slug) %}
      {% if im %}<img class="cover" src="{{ im }}" alt="{{ g.name }}" loading="lazy">
      {% else %}<div class="emblem">{{ g.short }}</div>{% endif %}
      <h3>{{ g.name }}</h3>
      <small>{{ g.currency }} mulai {{ g.packages[0][1] | rp }}</small>
      <span class="go">TOP UP SEKARANG ›</span>
    </a>
  {% endfor %}
  </div>
</div></section>

<section id="why"><div class="wrap">
  <h2>Kenapa RAFFZ GAME?</h2>
  <div class="feat">
    <div><h4>Proses instan</h4><p>Pesanan diproses otomatis begitu pembayaran terkonfirmasi.</p></div>
    <div><h4>Harga jelas</h4><p>Total dan biaya admin tampil sebelum kamu bayar. Tanpa biaya tersembunyi.</p></div>
    <div><h4>Banyak metode bayar</h4><p>QRIS, e-wallet, virtual account, sampai bayar di minimarket.</p></div>
    <div><h4>Tanpa login</h4><p>Cukup masukkan ID game. Akun dan password game tidak pernah diminta.</p></div>
  </div>
</div></section>
{% endblock %}"""

GAME = r"""{% extends "base.html" %}
{% block title %}Top up {{ g.name }} - RAFFZ GAME{% endblock %}
{% block body %}
<div class="wrap">
  <div class="banner" style="--c:{{ g.color }};--c2:{{ g.color2 }}">
    {% set im = game_img(g.slug) %}
    {% if im %}<img class="cover sm" src="{{ im }}" alt="{{ g.name }}">
    {% else %}<div class="emblem">{{ g.short }}</div>{% endif %}
    <div><h1>{{ g.name }}</h1><p>{{ g.desc }}</p></div>
  </div>
  <div class="top" style="--c:{{ g.color }}">
    <div>
      <div class="box"><h3><i>1</i>Masukkan data akun</h3>
        <div class="fields">
        {% for f in g.fields %}
          <label class="f"><span>{{ f.label }}</span>
          <input type="text" id="f_{{ f.name }}" placeholder="{{ f.ph }}" autocomplete="off">
          <div class="err" id="e_{{ f.name }}"></div></label>
        {% endfor %}
        </div>
      </div>
      <div class="box"><h3><i>2</i>Pilih nominal {{ g.currency }}</h3>
        <div class="opts">
        {% for p in g.pk %}
          <label class="opt"><input type="radio" name="pk" value="{{ p.id }}">
          <div><b>{{ "{:,}".format(p.amount).replace(",", ".") }}</b><small>{{ g.currency }}</small>
          <em>{{ p.price | rp }}</em></div></label>
        {% endfor %}
        </div>
      </div>
      <div class="box"><h3><i>3</i>Pilih pembayaran</h3>
        <div class="opts">
        {% for k, p in pay.items() %}
          <label class="opt"><input type="radio" name="pay" value="{{ k }}">
          <div><b>{{ p.name }}</b><small>{{ p.note }}</small></div></label>
        {% endfor %}
        </div>
      </div>
    </div>

    <aside class="box sum"><h3><i>4</i>Ringkasan</h3>
      <dl>
        <dt>Game</dt><dd>{{ g.name }}</dd>
        <dt>Item</dt><dd id="s_item">-</dd>
        <dt>Pembayaran</dt><dd id="s_pay">-</dd>
        <dt>Harga</dt><dd id="s_price">-</dd>
        <dt>Biaya admin</dt><dd id="s_fee">-</dd>
      </dl>
      <hr>
      <dl><dt>Total</dt><dd class="total" id="s_total">Rp 0</dd></dl>
      <div class="err" id="e_main"></div>
      <button class="btn" id="buy" type="button">BELI SEKARANG</button>
    </aside>
  </div>
</div>

<script>
const G = {{ g | tojson }};
const PAY = {{ pay | tojson }};
const $ = id => document.getElementById(id);
const rp = n => "Rp " + Math.round(n).toLocaleString("id-ID");
const pick = name => document.querySelector(`input[name=${name}]:checked`);

function calc(){
  const pk = pick("pk"), py = pick("pay");
  const price = pk ? G.pk[+pk.value].price : 0;
  const fee = py ? Math.ceil(price * PAY[py.value].pct / 100) + PAY[py.value].flat : 0;
  $("s_item").textContent = pk ? G.pk[+pk.value].amount.toLocaleString("id-ID") + " " + G.currency : "-";
  $("s_pay").textContent = py ? PAY[py.value].name : "-";
  $("s_price").textContent = pk ? rp(price) : "-";
  $("s_fee").textContent = py && pk ? rp(fee) : "-";
  $("s_total").textContent = rp(price + fee);
}
document.querySelectorAll("input[type=radio]").forEach(r => r.addEventListener("change", calc));

$("buy").addEventListener("click", async () => {
  const btn = $("buy"); $("e_main").textContent = "";
  const body = {game: G.slug, pk: pick("pk")?.value ?? null, pay: pick("pay")?.value ?? null, fields: {}};
  G.fields.forEach(f => body.fields[f.name] = $("f_" + f.name).value.trim());
  btn.disabled = true; btn.textContent = "MEMPROSES...";
  try {
    const res = await fetch("/api/order", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await res.json();
    G.fields.forEach(f => { $("e_" + f.name).textContent = (data.errors || {})[f.name] || ""; $("f_" + f.name).classList.toggle("bad", !!(data.errors || {})[f.name]); });
    if (!res.ok) { $("e_main").textContent = (data.errors || {}).main || "Periksa kembali data yang kamu isi."; }
    else { location.href = data.url; return; }
  } catch (e) { $("e_main").textContent = "Gagal terhubung ke server. Coba lagi."; }
  btn.disabled = false; btn.textContent = "BELI SEKARANG";
});
</script>
{% endblock %}"""

ORDER = r"""{% extends "base.html" %}
{% block title %}Pesanan {{ o.id }} - RAFFZ GAME{% endblock %}
{% block body %}
<div class="wrap"><div class="box invoice">
  <h2>Pesanan {{ o.id }}</h2>
  <p><span class="status {{ 'st-success' if o.status == 'success' else 'st-pending' }}" id="st">
    {{ 'Berhasil' if o.status == 'success' else 'Menunggu pembayaran' }}</span></p>
  <div class="row"><span>Game</span><span>{{ o.game }}</span></div>
  {% for k, v in o.fields.items() %}<div class="row"><span>{{ k }}</span><span>{{ v }}</span></div>{% endfor %}
  <div class="row"><span>Item</span><span>{{ o.item }}</span></div>
  <div class="row"><span>Pembayaran</span><span>{{ o.pay }}</span></div>
  <div class="row"><span>Harga</span><span>{{ o.price | rp }}</span></div>
  <div class="row"><span>Biaya admin</span><span>{{ o.fee | rp }}</span></div>
  <div class="row"><b>Total</b><b class="total" style="font-size:20px">{{ o.total | rp }}</b></div>
  <p style="color:var(--muted)" id="hint">
    {% if o.status == 'success' %}Item sudah dikirim ke akun kamu. Selamat bermain!
    {% else %}Ini mode demo. Klik tombol di bawah untuk mensimulasikan pembayaran berhasil.{% endif %}</p>
  {% if o.status != 'success' %}<button class="btn" id="pay" type="button">SIMULASI BAYAR</button>{% endif %}
  <a class="btn ghost" href="/" style="margin-left:6px">Kembali ke beranda</a>
</div></div>
{% if o.status != 'success' %}
<script>
document.getElementById("pay").addEventListener("click", async () => {
  const r = await fetch("/api/order/{{ o.id }}/pay", {method: "POST"});
  if (r.ok) location.reload();
});
</script>
{% endif %}
{% endblock %}"""

app.jinja_loader = DictLoader({"base.html": BASE, "home.html": HOME, "game.html": GAME, "order.html": ORDER})

# ----------------------------------------------------------------------------
# ROUTES
# ----------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html", games=GAMES)


@app.route("/game/<slug>")
def game(slug):
    if slug not in GAMES:
        abort(404)
    return render_template("game.html", g=game_view(slug), pay=PAYMENTS)


@app.post("/api/order")
def create_order():
    data = request.get_json(silent=True) or {}
    slug = data.get("game")
    if slug not in GAMES:
        return jsonify(errors={"main": "Game tidak ditemukan."}), 400
    g = GAMES[slug]
    errors, fields = {}, {}

    for f in g["fields"]:
        val = str((data.get("fields") or {}).get(f["name"], "")).strip()
        if not re.match(f["re"], val):
            errors[f["name"]] = f["err"]
        fields[f["label"]] = val

    try:
        pk = g["packages"][int(data.get("pk"))]
    except (TypeError, ValueError, IndexError):
        pk = None
        errors["main"] = "Pilih nominal top up terlebih dahulu."
    pay = PAYMENTS.get(data.get("pay"))
    if not pay and "main" not in errors:
        errors["main"] = "Pilih metode pembayaran terlebih dahulu."

    if errors:
        return jsonify(errors=errors), 400

    amount, price = pk
    fee = -(-price * pay["pct"] // 100) + pay["flat"]  # pembulatan ke atas
    order_id = "NX" + time.strftime("%y%m%d") + uuid.uuid4().hex[:6].upper()
    ORDERS[order_id] = {
        "id": order_id, "game": g["name"], "fields": fields,
        "item": f"{amount:,} {g['currency']}".replace(",", "."),
        "pay": pay["name"], "price": price, "fee": int(fee),
        "total": int(price + fee), "status": "pending",
    }
    return jsonify(url=f"/order/{order_id}")


@app.post("/api/order/<oid>/pay")
def pay_order(oid):
    if oid not in ORDERS:
        abort(404)
    ORDERS[oid]["status"] = "success"  # demo: di produksi diubah lewat webhook payment gateway
    return jsonify(ok=True)


@app.route("/order/<oid>")
def order(oid):
    if oid not in ORDERS:
        abort(404)
    return render_template("order.html", o=ORDERS[oid])


if __name__ == "__main__":
    app.run(debug=True)
