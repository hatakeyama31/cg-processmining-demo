import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import random
import requests

st.set_page_config(
    page_title="NeXT Diagnostics – 支払業務プロセス分析",
    page_icon="💰", layout="wide",
    initial_sidebar_state="expanded"
)

NAVY  = "#1A2B45"; STEEL = "#3F7AB0"; PALE  = "#EBF3FA"
WARN  = "#C05A20"; GREEN = "#1A6B3C"; LGRAY = "#F3F5F8"; MGRAY = "#7A8A9A"
ACCENT= "#8E3B6B"
AMBER = "#B8860B"; TEAL="#2E7D6B"; SLATE="#5C6B7A"

st.markdown(f"""<style>
  .main .block-container{{padding-top:1.5rem}}
  .kpi{{background:white;border-radius:10px;padding:1.1rem 1.4rem;
        border-left:4px solid {STEEL};box-shadow:0 1px 4px rgba(0,0,0,0.07)}}
  .kpi-w{{border-left-color:{WARN}}} .kpi-g{{border-left-color:{GREEN}}}
  .kpi-lbl{{font-size:11px;color:#7A8A9A;font-weight:600;letter-spacing:.05em;
            text-transform:uppercase;margin-bottom:4px}}
  .kpi-val{{font-size:30px;font-weight:700;color:{NAVY};line-height:1.1}}
  .kpi-sub{{font-size:11px;color:#AAB5C0;margin-top:3px}}
  .sec{{font-size:14px;font-weight:600;color:{NAVY};border-left:4px solid {STEEL};
        padding-left:10px;margin:16px 0 10px}}
  .stepnum{{display:inline-block;background:{NAVY};color:white;border-radius:50%;
        width:22px;height:22px;text-align:center;line-height:22px;font-size:12px;
        font-weight:700;margin-right:8px}}
  .subsec{{font-size:12px;font-weight:600;color:{MGRAY};margin:2px 0 8px 2px}}
  .ai-box{{background:{PALE};border-radius:10px;padding:1.4rem 1.6rem;
           border:1px solid #C0D4E8;line-height:1.8;font-size:14px}}
  .hint{{background:{LGRAY};border-radius:8px;padding:.9rem 1.2rem;
         color:#8A9AAA;font-size:13px}}
  .issue-card{{background:white;border-radius:10px;padding:1.0rem 1.2rem;
        border-top:3px solid {ACCENT};box-shadow:0 1px 4px rgba(0,0,0,0.07);height:100%}}
  .issue-title{{font-size:13px;font-weight:700;color:{NAVY};margin-bottom:6px}}
  .issue-body{{font-size:12.5px;color:#4A5A6A;line-height:1.65}}
  .issue-num{{font-size:22px;font-weight:700;color:{ACCENT};margin-right:4px}}
</style>""", unsafe_allow_html=True)

# ── 不一致パターンの定義（現状の事実情報のみ。AIの関与はここには含めない） ──
EXC_TYPES = {
    "数量差異":   dict(color=WARN,  dept="発注部門", days=(2.5,4.8), rejoin=True,
                       desc="発注した数量と、検収・請求書の数量が異なる"),
    "価格差異":   dict(color=AMBER, dept="購買部門", days=(3.2,6.0), rejoin=True,
                       desc="発注時点の価格と、請求書の価格が異なる"),
    "検収未登録": dict(color=TEAL,  dept="倉庫",     days=(1.2,3.5), rejoin=True,
                       desc="請求書は届いているが、検収の記録がまだない"),
    "重複請求書": dict(color=SLATE, dept="経理担当", days=(0.5,1.5), rejoin=False,
                       desc="同じ内容の請求書が二重に届いている"),
}

# ── 改善提案側でのみ使うAIアクション定義（現状フローには含めない） ──
AI_ACTIONS = {
    "数量差異":   dict(ai="仕入先への確認メールを<br>自動ドラフト",
                       human="発注部門が内容確認の<br>うえ送信"),
    "価格差異":   dict(ai="発注・請求の差額と変更<br>履歴を自動整理",
                       human="購買担当が価格変更<br>合意の有無を確認"),
    "検収未登録": dict(ai="倉庫の入荷記録へ<br>自動照会",
                       human="倉庫担当が実物確認の<br>うえ検収登録"),
    "重複請求書": dict(ai="過去の支払履歴と自動<br>照合し重複スコア算出",
                       human="経理担当が最終確認の<br>うえ棄却"),
}

# ── DATA ──────────────────────────────────────────────
@st.cache_data
def generate_data():
    random.seed(7); np.random.seed(7)
    VENDORS = [f"取引先{c}" for c in "ABCDEFGHIJ"]
    DEPTS_BUY = ["資材調達課","生産管理課","設備管理課"]
    n = 620
    rows = []
    base = datetime(2025,10,1)
    match_choices = ["一致"] + list(EXC_TYPES.keys())
    # Ardent Partners "AP Metrics That Matter 2025" 等のベンチマークに基づき、
    # 平均的な企業の請求書例外率は概ね20%前後（ベストプラクティス企業は一桁台）とされる。
    # ここでは典型的な中小企業を想定し、例外率合計 約20% で構成する。
    weights = [0.80, 0.07, 0.06, 0.05, 0.02]
    for i in range(n):
        vendor = random.choice(VENDORS)
        buy_dept = random.choice(DEPTS_BUY)
        po_amount = round(np.random.lognormal(mean=11.5, sigma=1.0),0)
        result = random.choices(match_choices, weights=weights)[0]
        invoice_date = base + timedelta(days=random.randint(0,150))

        if result=="一致":
            resolve_days = round(np.random.uniform(0.2,0.8),1)
            ai_used=False; rejected=False
        else:
            lo,hi = EXC_TYPES[result]["days"]
            resolve_days = round(np.random.uniform(lo,hi),1)
            ai_used = random.random()<0.82
            rejected = (result=="重複請求書")

        amount_band = "少額" if po_amount<300000 else ("中額" if po_amount<1500000 else "高額")
        pattern_match = np.clip(np.random.beta(5,2) if result!="一致" else np.random.beta(6,1.5),0,1)

        rows.append({
            "invoice_id": f"INV{i+1:05d}", "vendor": vendor, "buy_dept": buy_dept,
            "po_amount": po_amount, "amount_band": amount_band,
            "match_result": result, "resolve_days": resolve_days,
            "ai_used": ai_used, "rejected": rejected,
            "pattern_match": round(pattern_match,2),
            "invoice_date": invoice_date,
        })
    return pd.DataFrame(rows)

df = generate_data()

# ── ①現状プロセス可視化（プロセスマイニング。AI要素は含めない） ──
def make_asis_flow(fdf):
    n = len(fdf)
    match_rate = (fdf["match_result"]=="一致").mean()

    BW, BH = 2.6, 0.78
    FS_MAIN, FS_SUB, FS_LEGEND = 20, 14, 13.5

    trunk = [
        ("order", "発注",                    14.0),
        ("uke",   "検収",                    11.2),
        ("check", "請求書チェック<br>（発注・検収と照合）", 8.0),
        ("appr",  "支払確認",                -2.6),
        ("pay",   "支払実行",                -5.0),
    ]
    pos = {k:(0.0,y) for k,_,y in trunk}

    fig = go.Figure()
    fig.update_layout(
        height=1450, margin=dict(t=10,b=10,l=10,r=10),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(range=[-3.0,16.5],showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(range=[-6.0,17.0],showgrid=False,zeroline=False,showticklabels=False),
        showlegend=False, font=dict(family="Yu Gothic UI")
    )

    main_seq = ["order","uke","check"]
    for i in range(len(main_seq)-1):
        ay = pos[main_seq[i]][1]; by = pos[main_seq[i+1]][1]
        fig.add_annotation(x=0,y=by+BH,ax=0,ay=ay-BH,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=1.2,arrowwidth=3,
            arrowcolor=STEEL,showarrow=True,text="")

    fig.add_annotation(x=0,y=pos["appr"][1]+BH,ax=0,ay=pos["check"][1]-BH,
        xref="x",yref="y",axref="x",ayref="y",
        arrowhead=2,arrowsize=1.2,arrowwidth=4,
        arrowcolor=GREEN,showarrow=True,text="")
    fig.add_annotation(x=1.3,y=(pos["appr"][1]+pos["check"][1])/2,
        text=f"内容一致 {match_rate:.0%}", showarrow=False,
        font=dict(size=FS_SUB,color=GREEN), bgcolor="rgba(255,255,255,0.9)", borderpad=2)

    fig.add_annotation(x=0,y=pos["pay"][1]+BH,ax=0,ay=pos["appr"][1]-BH,
        xref="x",yref="y",axref="x",ayref="y",
        arrowhead=2,arrowsize=1.2,arrowwidth=3,
        arrowcolor=STEEL,showarrow=True,text="")

    # 不一致パターン別の分岐（件数・処理時間・対応部署のみを表示。AI要素は含めない）
    # 行き（検知→各分岐）は起点をずらして扇状に、戻り（各分岐→検知）は半径の異なる
    # 弧を使い、実際に請求書チェックの上端へ着地させることで手戻りだと分かるようにする。
    branch_ys = {"数量差異":6.4, "価格差異":4.0, "検収未登録":1.6, "重複請求書":-0.8}
    bx = 6.9   # 検知ボックス右端（BW=2.6）との間に十分な隙間を確保し、扇状分岐を成立させる
    BBW, BBH = 2.0, 0.95
    rejoin_i = 0
    n_rejoin = sum(1 for c in EXC_TYPES.values() if c["rejoin"])
    for idx,(exc,by) in enumerate(branch_ys.items()):
        cfg = EXC_TYPES[exc]
        sub = fdf[fdf["match_result"]==exc]
        rate = len(sub)/n
        avg_days = sub["resolve_days"].mean() if len(sub) else 0
        color = cfg["color"]

        # 検知ノードから各分岐へ（起点を右端に沿ってずらし、隙間の中で扇状に独立して伸ばす）
        origin_y = pos['check'][1] + BH*0.8 - idx*(BH*1.6/3)
        fig.add_annotation(x=bx-BBW,y=by,ax=BW,ay=origin_y,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=1.0,arrowwidth=2.6,
            arrowcolor=color,showarrow=True,text="")

        fig.add_shape(type="rect",x0=bx-BBW,y0=by-BBH,x1=bx+BBW,y1=by+BBH,
            fillcolor=color,line=dict(color="white",width=1.3),layer="above")
        fig.add_annotation(x=bx,y=by+0.55,text=f"<b>{exc}</b>",
            showarrow=False,font=dict(size=FS_SUB,color="white"),align="center")
        fig.add_annotation(x=bx,y=by+0.12,text=f"{cfg['dept']}が対応",
            showarrow=False,font=dict(size=12,color="rgba(255,255,255,0.95)"),align="center")
        fig.add_annotation(x=bx,y=by-0.35,
            text=f"件数 {len(sub)}件（{rate:.0%}）　平均{avg_days:.1f}日",
            showarrow=False,font=dict(size=11.5,color="rgba(255,255,255,0.95)"),align="center")

        if cfg["rejoin"]:
            # 戻り経路は「右へ抜ける→ボックス群の外側を上へ→検知ボックス上端へ」という
            # 明確な迂回ルートにする。ボックスの上を横切らないため重ならず、
            # 着地点も検知ボックスの上端に近接させて揃え、見た目を統一する。
            far_x   = bx + BBW + 1.6 + rejoin_i*1.3
            top_y   = pos['check'][1] + BH + 0.7 + rejoin_i*0.24
            entry_x = -0.4 + rejoin_i*0.4
            entry_y = pos['check'][1] + BH
            sx, sy = bx+BBW, by
            path = (f"M {sx} {sy} L {far_x} {sy} L {far_x} {top_y} "
                    f"L {entry_x} {top_y} L {entry_x} {entry_y}")
            fig.add_shape(type="path", path=path,
                line=dict(color=color,width=2.4,dash="dashdot"), layer="above")
            fig.add_annotation(x=entry_x,y=entry_y,ax=entry_x,ay=entry_y+0.3,
                xref="x",yref="y",axref="x",ayref="y",
                arrowhead=2,arrowsize=1.0,arrowwidth=2.4,
                arrowcolor=color,showarrow=True,text="")
            fig.add_annotation(x=far_x+0.15,y=(sy+top_y)/2,
                text=f"対応後、請求書<br>チェックへ差し戻し",
                showarrow=False,font=dict(size=10.5,color=color),align="left",xanchor="left",
                bgcolor="rgba(255,255,255,0.88)",borderpad=1)
            rejoin_i += 1
        else:
            tx = bx+BBW+2.2
            fig.add_shape(type="path",path=f"M {bx+BBW} {by} L {tx-1.1} {by}",
                line=dict(color=color,width=2.2),layer="above")
            fig.add_annotation(x=tx-1.1,y=by,ax=bx+BBW,ay=by,
                xref="x",yref="y",axref="x",ayref="y",
                arrowhead=2,arrowsize=1.0,arrowwidth=2.2,
                arrowcolor=color,showarrow=True,text="")
            fig.add_shape(type="rect",x0=tx-1.1,y0=by-0.68,x1=tx+1.1,y1=by+0.68,
                fillcolor=MGRAY,line=dict(color="white",width=1.3),layer="above")
            fig.add_annotation(x=tx,y=by,text="<b>支払わず</b><br>棄却",
                showarrow=False,font=dict(size=12.5,color="white"),align="center")


    for key,label,y in trunk:
        fill = GREEN if key in ("appr","pay") else (ACCENT if key=="check" else NAVY)
        w = BW*1.1 if key=="check" else BW
        fig.add_shape(type="rect",x0=-w,y0=y-BH,x1=w,y1=y+BH,
            fillcolor=fill,line=dict(color="white",width=1.5),layer="above")
        fig.add_annotation(x=0,y=y,text=f"<b>{label}</b>",
            showarrow=False,font=dict(size=FS_MAIN,color="white"),align="center")

    fig.add_annotation(x=-2.8,y=15.3,xref="x",yref="y",xanchor="left",
        text="請求書チェックの時点で、発注・検収・請求書の内容を突き合わせる",
        showarrow=False,font=dict(size=FS_LEGEND,color=MGRAY),align="left")

    return fig

# ── ②課題による影響のまとめ ──────────────────────────────
def build_impact_table(fdf):
    n_total = len(fdf)
    exc_df = fdf[fdf["match_result"]!="一致"]
    rows = []
    for exc,cfg in EXC_TYPES.items():
        sub = fdf[fdf["match_result"]==exc]
        rows.append({
            "不一致パターン": exc, "対応部署": cfg["dept"],
            "件数": len(sub), "発生率": f"{len(sub)/n_total:.1%}",
            "平均対応日数": round(sub["resolve_days"].mean(),1) if len(sub) else 0,
            "滞留金額合計": int(sub["po_amount"].sum()),
            "延べ対応日数": round((sub["resolve_days"]).sum(),1),
        })
    return pd.DataFrame(rows)

# ── ③AIを使った効率化（改善提案。ここではじめてAIが登場） ──
# To-Beフロー：請求書チェックで検知された不一致それぞれについて、
# AIが「原因特定→下調べ・ドラフト作成」まで行い、人は最終確認・実行のみを行う。
# 種類ごとに対応内容が異なるため、4つの独立したレーンとして表現する
# （①のフローと同じ理由で、レーン同士が交差する線は使わない）。
def make_tobe_flow(fdf):
    BW, BH = 2.3, 0.7
    lane_x = {"数量差異":-5.1, "価格差異":-1.7, "検収未登録":1.7, "重複請求書":5.1}

    fig = go.Figure()
    fig.update_layout(
        height=1050, margin=dict(t=10,b=10,l=10,r=10),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(range=[-7.0,7.0],showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(range=[-1.0,9.6],showgrid=False,zeroline=False,showticklabels=False),
        showlegend=False, font=dict(family="Yu Gothic UI")
    )
    fig.add_annotation(x=-6.8,y=9.2,xref="x",yref="y",xanchor="left",
        text="実線＝AIが自動で行う部分（ログに残る）　　点線枠＝人が確認・実行する部分",
        showarrow=False,font=dict(size=13,color=MGRAY),align="left")

    # 起点：請求書チェックで不一致を検知（1つの共有ノード。ここから4レーンへ分岐）
    origin_y = 7.7
    fig.add_shape(type="rect",x0=-2.6,y0=origin_y-BH,x1=2.6,y1=origin_y+BH,
        fillcolor=ACCENT,line=dict(color="white",width=1.5),layer="above")
    fig.add_annotation(x=0,y=origin_y,text="<b>請求書チェックで不一致を検知</b>",showarrow=False,
        font=dict(size=15,color="white"),align="center")

    ai_y, hu_y, done_y = 5.4, 2.7, 0.3
    for exc,lx in lane_x.items():
        cfg = EXC_TYPES[exc]; act = AI_ACTIONS[exc]
        color = cfg["color"]

        # 起点からレーンへ（直接の対角線のみ。他レーンと共有しない）
        fig.add_annotation(x=lx,y=ai_y+BH,ax=0,ay=origin_y-BH,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=1.0,arrowwidth=2.2,arrowcolor=color,showarrow=True,text="")

        fig.add_annotation(x=lx,y=ai_y+BH+0.35,text=f"<b>{exc}</b>",showarrow=False,
            font=dict(size=13,color=color),align="center")

        # AI下調べ（実線で接続＝自動）
        fig.add_shape(type="rect",x0=lx-BW,y0=ai_y-BH,x1=lx+BW,y1=ai_y+BH,
            fillcolor=color,line=dict(color="white",width=1.3),layer="above")
        fig.add_annotation(x=lx,y=ai_y+0.25,text="<b>AI下調べ</b>",showarrow=False,
            font=dict(size=12,color="white"),align="center")
        fig.add_annotation(x=lx,y=ai_y-0.28,text=act["ai"],showarrow=False,
            font=dict(size=10.8,color="rgba(255,255,255,0.95)"),align="center")

        fig.add_annotation(x=lx,y=hu_y+BH,ax=lx,ay=ai_y-BH,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=1.0,arrowwidth=2.2,arrowcolor=color,showarrow=True,text="")

        # 人が確認・実行（点線枠＝オフシステムの人手対応）
        fig.add_shape(type="rect",x0=lx-BW,y0=hu_y-BH,x1=lx+BW,y1=hu_y+BH,
            fillcolor="white",line=dict(color=color,width=2.6,dash="dot"),layer="above")
        fig.add_annotation(x=lx,y=hu_y+0.25,text=f"<b>{cfg['dept']}が対応</b>",showarrow=False,
            font=dict(size=12,color=color),align="center")
        fig.add_annotation(x=lx,y=hu_y-0.28,text=act["human"],showarrow=False,
            font=dict(size=10.8,color=SLATE),align="center")

        fig.add_annotation(x=lx,y=done_y+0.35,ax=lx,ay=hu_y-BH,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=0.9,arrowwidth=2.0,arrowcolor=color,showarrow=True,text="")
        fig.add_annotation(x=lx,y=done_y,text="対応完了・<br>再チェックへ",showarrow=False,
            font=dict(size=10.5,color=color),align="center")

    return fig

# ── 経理担当者向け照合チェックリスト（仮） ──────────────
def build_checklist(fdf):
    rows = []
    for exc,cfg in EXC_TYPES.items():
        act = AI_ACTIONS[exc]
        ai_plain = act["ai"].replace("<br>","")
        human_plain = act["human"].replace("<br>","")
        rows.append({
            "不一致区分": exc,
            "AIが用意する情報": ai_plain,
            "担当者が確認すること": human_plain,
            "担当部署": cfg["dept"],
        })
    tbl = pd.DataFrame(rows)
    return tbl



def make_routing_chart(fdf):
    exc = fdf[fdf["match_result"]!="一致"].copy()

    def zone(row):
        if row["po_amount"]<300000 and row["pattern_match"]>=0.6:
            return "自動処理ゾーン"
        elif row["pattern_match"]>=0.4:
            return "AI推奨＋人が承認"
        else:
            return "人手調査ゾーン"
    exc["zone"] = exc.apply(zone,axis=1)

    colors = {"自動処理ゾーン":GREEN,"AI推奨＋人が承認":AMBER,"人手調査ゾーン":WARN}
    fig = go.Figure()
    for z,c in colors.items():
        sub = exc[exc["zone"]==z]
        fig.add_trace(go.Scatter(
            x=sub["pattern_match"], y=sub["po_amount"], mode="markers",
            marker=dict(color=c,size=8,opacity=0.65,line=dict(width=0)),
            name=z,
            hovertemplate="過去パターン一致度: %{x:.2f}<br>金額: ¥%{y:,.0f}<extra></extra>"
        ))
    fig.update_layout(
        height=420, margin=dict(t=20,b=40,l=60,r=20),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis_title="過去の類似パターンとの一致度（低←→高）",
        yaxis_title="請求金額（円）",
        yaxis_type="log",
        legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="left",x=0),
        font=dict(family="Yu Gothic UI",size=12)
    )
    fig.update_xaxes(gridcolor="#EEF2F6",range=[0,1])
    fig.update_yaxes(gridcolor="#EEF2F6")
    return fig

# ── SIDEBAR ───────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='font-size:22px;font-weight:700;color:{NAVY};'>"
                f"NeXT<span style='color:{STEEL};'> Diagnostics</span></div>",
                unsafe_allow_html=True)
    st.caption("支払業務プロセス分析 Demo v2.0")
    st.divider()
    depts = ["全部門"] + sorted(df["buy_dept"].unique())
    sel = st.selectbox("発注部門で絞り込み", depts)
    st.divider()
    api_key = st.text_input("Claude API Key", type="password", placeholder="sk-ant-...")
    st.caption("AI分析機能の利用に必要です")

fdf = df if sel=="全部門" else df[df["buy_dept"]==sel]

# ── TITLE ─────────────────────────────────────────────
st.markdown("## 💰 支払業務プロセス分析ダッシュボード")
st.caption(f"{sel}　｜　{len(fdf):,} 件の請求書処理　｜　発注 → 検収 → 請求書チェック → 支払　｜　デモデータ")

n_total = len(fdf)
match_rate = (fdf["match_result"]=="一致").mean()*100
exc_df = fdf[fdf["match_result"]!="一致"]
avg_resolve = exc_df["resolve_days"].mean() if len(exc_df) else 0

c1,c2,c3,c4 = st.columns(4)
for col,lbl,val,sub,cls in [
    (c1,"総処理件数",       f"{n_total:,}件",     "分析対象の請求書処理",  ""),
    (c2,"一発で一致する割合", f"{match_rate:.0f}%", "発注・検収・請求書が即一致","kpi-g" if match_rate>=55 else "kpi-w"),
    (c3,"不一致件数",       f"{len(exc_df):,}件", "人の対応が必要な件数",  "kpi-w"),
    (c4,"不一致の平均対応日数", f"{avg_resolve:.1f}日","一致から解決までの日数","kpi-w" if avg_resolve>3 else ""),
]:
    with col:
        st.markdown(f"<div class='kpi {cls}'><div class='kpi-lbl'>{lbl}</div>"
                    f"<div class='kpi-val'>{val}</div>"
                    f"<div class='kpi-sub'>{sub}</div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── ① 現状可視化 ───────────────────────────────────────
st.markdown("<div class='sec'><span class='stepnum'>1</span>現状プロセスの可視化（プロセスマイニング）</div>",
            unsafe_allow_html=True)
st.markdown("<div class='subsec'>実際の処理データから、そのままの姿を可視化。この段階ではAIは使っていない</div>",
            unsafe_allow_html=True)
st.plotly_chart(make_asis_flow(fdf), use_container_width=True)

# ── ② 影響のまとめ ─────────────────────────────────────
st.markdown("<div class='sec'><span class='stepnum'>2</span>課題による影響のまとめ</div>",
            unsafe_allow_html=True)
impact_tbl = build_impact_table(fdf)
st.dataframe(impact_tbl, hide_index=True, use_container_width=True)

total_stuck = impact_tbl["滞留金額合計"].sum()
total_days = impact_tbl["延べ対応日数"].sum()
worst = impact_tbl.loc[impact_tbl["延べ対応日数"].idxmax()]

i1,i2,i3 = st.columns(3)
with i1:
    st.markdown(f"""<div class='issue-card'>
        <div class='issue-title'>滞留している金額</div>
        <div class='issue-body'><span class='issue-num'>¥{total_stuck:,.0f}</span><br>
        不一致のまま処理が止まっている請求書の合計金額。支払遅延や資金繰りに直結する。</div></div>""",
        unsafe_allow_html=True)
with i2:
    st.markdown(f"""<div class='issue-card'>
        <div class='issue-title'>最も負荷の大きいパターン</div>
        <div class='issue-body'><span class='issue-num'>{worst['不一致パターン']}</span><br>
        延べ{worst['延べ対応日数']:.0f}日分の対応工数が発生（{worst['対応部署']}）。
        優先的に手を打つべき箇所。</div></div>""", unsafe_allow_html=True)
with i3:
    st.markdown(f"""<div class='issue-card'>
        <div class='issue-title'>合計の対応工数</div>
        <div class='issue-body'><span class='issue-num'>{total_days:.0f}日</span><br>
        不一致対応にかかっている延べ日数の合計。人手で吸収してきた"見えないコスト"。</div></div>""",
        unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── ③ AIを使った効率化 ─────────────────────────────────
st.markdown("<div class='sec'><span class='stepnum'>3</span>AIを使った効率化（改善提案）</div>",
            unsafe_allow_html=True)
st.markdown("<div class='subsec'>①②で見えた課題に対して、AIが「差異の特定・情報整理・下調べ」まで行い、"
            "人は最終確認と、AIも判断できない案件の調査だけを行う、という役割分担のイメージ</div>",
            unsafe_allow_html=True)
st.plotly_chart(make_tobe_flow(fdf), use_container_width=True)

st.markdown("<div class='subsec' style='margin-top:10px'>経理担当者向け 照合チェックリスト（仮）</div>",
            unsafe_allow_html=True)
st.dataframe(build_checklist(fdf), hide_index=True, use_container_width=True)

st.markdown("<div class='subsec' style='margin-top:14px'>参考：金額 × 過去パターンとの一致度で、"
            "自動処理／AI推奨＋人承認／人手調査、に仕分ける考え方</div>", unsafe_allow_html=True)
st.plotly_chart(make_routing_chart(fdf), use_container_width=True)

r1,r2,r3 = st.columns(3)
with r1:
    st.markdown(f"""<div class='issue-card' style='border-top-color:{GREEN}'>
        <div class='issue-title'>自動処理ゾーン</div>
        <div class='issue-body'>少額かつ過去に何度も見たパターン。AIが下調べから解決案の適用まで
        完結し、人は事後サンプリングでチェックするだけで良い。</div></div>""", unsafe_allow_html=True)
with r2:
    st.markdown(f"""<div class='issue-card' style='border-top-color:{AMBER}'>
        <div class='issue-title'>AI推奨＋人が承認</div>
        <div class='issue-body'>AIが下調べ・ドラフトまで作成するが、最終判断と送信は必ず人が行う。</div></div>""",
        unsafe_allow_html=True)
with r3:
    st.markdown(f"""<div class='issue-card' style='border-top-color:{WARN}'>
        <div class='issue-title'>人手調査ゾーン</div>
        <div class='issue-body'>高額、または過去に類似パターンがない初見のケース。
        AIに任せず、担当者が一から事実確認する。</div></div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── AI診断 ────────────────────────────────────────────
st.markdown("<div class='sec'>🤖 AI プロセス診断（Claude API）</div>", unsafe_allow_html=True)

if st.button("▶ AI診断を実行", type="primary"):
    if not api_key:
        st.warning("サイドバーにClaude API Keyを入力してください。")
    else:
        prompt = f"""あなたは経理・内部統制に詳しいプロセス改善コンサルタントです。
以下の支払業務プロセスのデータを分析し、日本語で経営者向け診断レポートを作成してください。

【対象】{sel}
【総処理件数】{n_total}件　【一発一致率】{match_rate:.0f}%
【不一致件数】{len(exc_df)}件　【平均対応日数】{avg_resolve:.1f}日
【滞留金額合計】¥{total_stuck:,.0f}　【延べ対応日数】{total_days:.0f}日

【パターン別の内訳】
{impact_tbl.to_string(index=False)}

以下の構成で簡潔・具体的に答えてください：

## 🔍 最も改善余地の大きいパターン
## 📊 構造的な原因
## ✅ 即実行できる改善アクション（3つ）
## ⚠️ 資金繰り・支払遅延リスクの評価"""

        with st.spinner("Claudeが分析中...（10〜20秒）"):
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type":"application/json","x-api-key":api_key,
                             "anthropic-version":"2023-06-01"},
                    json={"model":"claude-sonnet-4-6","max_tokens":1200,
                          "messages":[{"role":"user","content":prompt}]},
                    timeout=40
                )
                if resp.status_code==200:
                    st.markdown(f"<div class='ai-box'>{resp.json()['content'][0]['text']}</div>",
                                unsafe_allow_html=True)
                else:
                    st.error(f"APIエラー {resp.status_code}: {resp.text}")
            except Exception as e:
                st.error(f"エラー: {e}")
else:
    st.markdown(f"""<div class='hint'>▶ ボタンを押すと Claudeがプロセスデータを分析し、
    <b>改善余地の大きいパターン・構造的原因・改善アクション・資金リスク評価</b>を自動生成します。
    サイドバーにClaude API Keyが必要です。</div>""", unsafe_allow_html=True)

st.divider()
st.caption("NeXT Diagnostics Demo v2.0（支払業務）｜ データはデモ用サンプルです")
