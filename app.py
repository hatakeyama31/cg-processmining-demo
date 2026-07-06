import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import random
import requests

st.set_page_config(
    page_title="NeXT Diagnostics – CG制作プロセス分析",
    page_icon="🎬", layout="wide",
    initial_sidebar_state="expanded"
)

NAVY  = "#1A2B45"; STEEL = "#3F7AB0"; PALE  = "#EBF3FA"
WARN  = "#C05A20"; GREEN = "#1A6B3C"; LGRAY = "#F3F5F8"; MGRAY = "#7A8A9A"
CLR   = dict(NAVY=NAVY,STEEL=STEEL,PALE=PALE,WARN=WARN,GREEN=GREEN,MGRAY=MGRAY)

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
  .ai-box{{background:{PALE};border-radius:10px;padding:1.4rem 1.6rem;
           border:1px solid #C0D4E8;line-height:1.8;font-size:14px}}
  .hint{{background:{LGRAY};border-radius:8px;padding:.9rem 1.2rem;
         color:#8A9AAA;font-size:13px}}
</style>""", unsafe_allow_html=True)

# ── STAGES (スライド27準拠) ─────────────────────────────
STAGES = ["要求仕様定義","モデリング","リギング","テクスチャリング",
          "レイアウト","アニメーション","ライティング","レンダリング","品質チェック"]
PLAN  = {"要求仕様定義":2,"モデリング":5,"リギング":3,"テクスチャリング":4,
         "レイアウト":3,"アニメーション":8,"ライティング":4,"レンダリング":2,"品質チェック":2}
REVRT = {"要求仕様定義":.10,"モデリング":.20,"リギング":.12,"テクスチャリング":.18,
         "レイアウト":.15,"アニメーション":.44,"ライティング":.29,"レンダリング":.16,"品質チェック":.22}

# ── DATA ──────────────────────────────────────────────
@st.cache_data
def generate_data():
    random.seed(42); np.random.seed(42)
    PROJS = [
        {"id":"P01","name":"PROJECT ALPHA","type":"TVアニメ","n":80},
        {"id":"P02","name":"PROJECT NOVA", "type":"劇場版",  "n":50},
        {"id":"P03","name":"PROJECT ECHO", "type":"OVA",    "n":40},
    ]
    ARTISTS = [f"Artist {c}" for c in "ABCDEFGH"]
    rows = []; sid = 1
    for pr in PROJS:
        base = datetime(2025,4,1)
        for _ in range(pr["n"]):
            cx  = random.choices(["低","中","高"], weights=[.3,.5,.2])[0]
            art = random.choice(ARTISTS)
            cur = base + timedelta(days=random.randint(0,90))
            for si,stg in enumerate(STAGES):
                pd_= PLAN[stg]; m={"低":.7,"中":1.0,"高":1.5}[cx]
                act= max(1.0, pd_*m+np.random.normal(0,pd_*.28))
                rev= 0
                if random.random()<REVRT[stg]:
                    rev= random.choices([1,2,3],weights=[.55,.3,.15])[0]
                    act+= rev*pd_*.55
                end= cur+timedelta(days=act)
                rows.append({"shot_id":f"CUT_{sid:04d}","project":pr["name"],
                    "type":pr["type"],"stage":stg,"stage_idx":si,"artist":art,
                    "complexity":cx,"planned":pd_,"actual":act,"revision":rev,
                    "delay":max(0.0,act-pd_),"is_late":act>pd_+.5,
                    "start":cur,"end":end})
                cur=end
            sid+=1
    return pd.DataFrame(rows)

df = generate_data()

# ── DFG NETWORK GRAPH ─────────────────────────────────
def make_dfg(fdf, stages):
    ALL  = stages + ["承認完了"]
    top  = stages[:5]   # 要求仕様定義..レイアウト
    bot  = stages[5:]   # アニメーション..品質チェック

    # Node center positions
    pos = {}
    for i,s in enumerate(top): pos[s] = (1.0+i*2.2, 1.8)
    for i,s in enumerate(bot):  pos[s] = (9.8-i*2.2, 0.2)
    pos["承認完了"] = (1.0, 0.2)

    # Per-node stats
    ns = fdf.groupby("stage").agg(
        n   =("shot_id","nunique"),
        act =("actual","mean"),
        pln =("planned","mean"),
        rev =("revision",lambda x:(x>0).mean()),
    ).reset_index().set_index("stage")

    NW, NH = 0.92, 0.23  # half-width, half-height

    fig = go.Figure()
    fig.update_layout(
        height=390, margin=dict(t=8,b=36,l=8,r=8),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(range=[-0.5,12.0],showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(range=[-0.85,2.65],showgrid=False,zeroline=False,showticklabels=False),
        showlegend=False,
        font=dict(family="Yu Gothic UI")
    )

    # ── Forward edges ──
    for i in range(len(ALL)-1):
        a,b = ALL[i],ALL[i+1]
        if a not in pos or b not in pos: continue
        ax,ay = pos[a]; bx,by = pos[b]
        n_c = int(ns.loc[a,"n"]) if a in ns.index else 50
        w   = max(1.5, min(5.0, n_c/20))

        if abs(ay-by)>0.3:      # vertical (レイアウト→アニメーション)
            sx_,sy_ = ax, ay-NH
            ex_,ey_ = bx, by+NH
        elif bx < ax:           # right→left (bottom row)
            sx_,sy_ = ax-NW, ay
            ex_,ey_ = bx+NW, by
        else:                   # left→right (top row)
            sx_,sy_ = ax+NW, ay
            ex_,ey_ = bx-NW, by

        fig.add_annotation(x=ex_,y=ey_,ax=sx_,ay=sy_,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=1.2,arrowwidth=w,
            arrowcolor=STEEL,showarrow=True,text="")

        # Edge label
        mx=(ax+bx)/2; my=(ay+by)/2+(0.18 if abs(ay-by)<0.3 else 0)
        if a in ns.index:
            fig.add_annotation(x=mx,y=my,
                text=f"{ns.loc[a,'act']:.1f}日",
                showarrow=False,font=dict(size=8,color=MGRAY),
                bgcolor="rgba(255,255,255,0.85)",borderpad=2)

    # ── Revision arcs (self-loops) ──
    for s in stages:
        if s not in pos or s not in ns.index: continue
        if ns.loc[s,"rev"] < 0.13: continue
        x,y = pos[s]; r = ns.loc[s,"rev"]
        if y>1.0:  # top row → arc above
            path=f"M {x+NW} {y+NH} C {x+NW*2.2} {y+0.72} {x-NW*0.6} {y+0.72} {x-NW} {y+NH}"
            ly=y+0.60
        else:      # bottom row → arc below
            path=f"M {x+NW} {y-NH} C {x+NW*2.2} {y-0.72} {x-NW*0.6} {y-0.72} {x-NW} {y-NH}"
            ly=y-0.60
        fig.add_shape(type="path",path=path,
            line=dict(color=WARN,width=2,dash="dot"),layer="above")
        fig.add_annotation(x=x+0.1,y=ly,
            text=f"↩ {r:.0%}",showarrow=False,
            font=dict(size=9,color=WARN),bgcolor="rgba(255,255,255,0.88)",borderpad=2)

    # ── Nodes (drawn on top) ──
    for s in ALL:
        if s not in pos: continue
        x,y = pos[s]
        if s=="承認完了":
            fill=GREEN
        elif s in ns.index:
            pct=(ns.loc[s,"act"]-ns.loc[s,"pln"])/ns.loc[s,"pln"]
            fill=WARN if pct>0.30 else STEEL if pct>0.10 else NAVY
        else:
            fill=NAVY

        fig.add_shape(type="rect",
            x0=x-NW,y0=y-NH,x1=x+NW,y1=y+NH,
            fillcolor=fill,line=dict(color="white",width=1.5),layer="above")

        lbl = s if len(s)<=7 else s[:6]+"…"
        fig.add_annotation(x=x,y=y+0.07,text=f"<b>{lbl}</b>",
            showarrow=False,font=dict(size=10,color="white"))
        if s in ns.index:
            fig.add_annotation(x=x,y=y-0.09,
                text=f"n={int(ns.loc[s,'n'])} | {ns.loc[s,'act']:.1f}日",
                showarrow=False,font=dict(size=8,color="rgba(255,255,255,0.85)"))
        elif s=="承認完了":
            fig.add_annotation(x=x,y=y-0.09,text="完了",
                showarrow=False,font=dict(size=8,color="rgba(255,255,255,0.85)"))

    # Legend
    fig.add_annotation(x=0,y=-0.75,xref="x",yref="y",
        text="🟦 標準　🟠 ボトルネック（計画比+30%超）　🟩 完了　⤾ リビジョンループ（発生率）",
        showarrow=False,font=dict(size=9,color=MGRAY))

    return fig

# ── SIDEBAR ───────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='font-size:22px;font-weight:700;color:{NAVY};'>"
                f"NeXT<span style='color:{STEEL};'> Diagnostics</span></div>",
                unsafe_allow_html=True)
    st.caption("CG制作プロセス分析 Demo v2.0")
    st.divider()
    projs = ["全プロジェクト"] + sorted(df["project"].unique())
    sel   = st.selectbox("プロジェクト選択", projs)
    st.divider()
    api_key = st.text_input("Claude API Key", type="password", placeholder="sk-ant-...")
    st.caption("AI分析機能の利用に必要です")

fdf = df if sel=="全プロジェクト" else df[df["project"]==sel]

# ── TITLE ─────────────────────────────────────────────
st.markdown("## 🎬 CG制作プロセス分析ダッシュボード")
st.caption(f"{sel}　｜　{fdf['shot_id'].nunique():,} ショット　｜　"
           f"工程: {' → '.join(STAGES[:4])} → …　｜　ShotGrid連携（デモデータ）")

# ── KPI ───────────────────────────────────────────────
shots     = fdf["shot_id"].nunique()
avg_delay = fdf.groupby("shot_id")["delay"].sum().mean()
total_rev = int(fdf["revision"].sum())
on_time   = (1-fdf.groupby("shot_id")["is_late"].any().mean())*100

c1,c2,c3,c4 = st.columns(4)
for col,lbl,val,sub,cls in [
    (c1,"分析ショット数",    f"{shots:,}",        "全工程のログを可視化",   ""),
    (c2,"平均遅延日数",       f"{avg_delay:.1f}日", "ショットあたり合計遅延","kpi-w" if avg_delay>3 else ""),
    (c3,"総リビジョン回数",  f"{total_rev:,}回",   "全工程・全ショット合計", "kpi-w"),
    (c4,"期限内完了率",       f"{on_time:.0f}%",    "全ショット・全工程",     "kpi-g" if on_time>=70 else "kpi-w"),
]:
    with col:
        st.markdown(f"<div class='kpi {cls}'><div class='kpi-lbl'>{lbl}</div>"
                    f"<div class='kpi-val'>{val}</div>"
                    f"<div class='kpi-sub'>{sub}</div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── DFG + Bottleneck ──────────────────────────────────
r2l, r2r = st.columns([3,2])

with r2l:
    st.markdown("<div class='sec'>プロセスフロー（DFG: 実態マップ）</div>",
                unsafe_allow_html=True)
    fig_dfg = make_dfg(fdf, STAGES)
    st.plotly_chart(fig_dfg, use_container_width=True)

with r2r:
    st.markdown("<div class='sec'>工程別ボトルネック（計画比）</div>",
                unsafe_allow_html=True)
    ss = fdf.groupby("stage").agg(actual=("actual","mean"),planned=("planned","mean")).reset_index()
    ss = ss[ss["stage"].isin(STAGES)]
    ss["stage"] = pd.Categorical(ss["stage"],categories=STAGES,ordered=True)
    ss = ss.sort_values("stage",ascending=True)
    ss["pct"] = (ss["actual"]-ss["planned"])/ss["planned"]*100
    
    fig_b = go.Figure(go.Bar(
        y=ss["stage"], x=ss["pct"], orientation="h",
        marker_color=[WARN if v>0 else GREEN for v in ss["pct"]],
        text=[f"{v:+.0f}%" for v in ss["pct"]], textposition="outside",
        hovertemplate="<b>%{y}</b><br>計画比: %{x:+.1f}%<extra></extra>"
    ))
    fig_b.add_vline(x=0,line_color=NAVY,line_width=1.5)
    fig_b.update_layout(
        height=390,margin=dict(t=8,b=8,l=10,r=65),
        paper_bgcolor="white",plot_bgcolor="white",
        xaxis_title="計画比（%）",
        font=dict(family="Yu Gothic UI",size=11)
    )
    fig_b.update_xaxes(gridcolor="#EEF2F6")
    st.plotly_chart(fig_b, use_container_width=True)

# ── Heatmap + Histogram ───────────────────────────────
r3l, r3r = st.columns([3,2])

with r3l:
    st.markdown("<div class='sec'>アーティスト × 工程　平均リビジョン回数</div>",
                unsafe_allow_html=True)
    hp = fdf.groupby(["artist","stage"])["revision"].mean().reset_index()
    pv = hp.pivot(index="artist",columns="stage",values="revision").fillna(0)
    pv = pv[[s for s in STAGES if s in pv.columns]]
    fig_h = go.Figure(go.Heatmap(
        z=pv.values, x=pv.columns.tolist(), y=pv.index.tolist(),
        colorscale=[[0,PALE],[0.4,STEEL],[1,WARN]],
        hovertemplate="<b>%{y} × %{x}</b><br>平均: %{z:.2f}回<extra></extra>",
        text=np.round(pv.values,1), texttemplate="%{text}",
        textfont=dict(size=10)
    ))
    fig_h.update_layout(height=290,margin=dict(t=8,b=8,l=10,r=10),
                        paper_bgcolor="white",
                        font=dict(family="Yu Gothic UI",size=10))
    st.plotly_chart(fig_h, use_container_width=True)

with r3r:
    st.markdown("<div class='sec'>ショット別　遅延日数の分布</div>",
                unsafe_allow_html=True)
    sd2 = fdf.groupby("shot_id")["delay"].sum().reset_index()
    avg_d = sd2["delay"].mean()
    fig_hist = px.histogram(sd2,x="delay",nbins=25,
        color_discrete_sequence=[STEEL],
        labels={"delay":"合計遅延日数","count":"ショット数"})
    fig_hist.add_vline(x=avg_d,line_dash="dash",line_color=WARN,
        annotation_text=f"平均 {avg_d:.1f}日",
        annotation_font_color=WARN,annotation_position="top right")
    fig_hist.update_layout(height=290,margin=dict(t=8,b=8,l=10,r=10),
        paper_bgcolor="white",plot_bgcolor="white",bargap=0.08,
        font=dict(family="Yu Gothic UI",size=11))
    fig_hist.update_yaxes(gridcolor="#EEF2F6")
    st.plotly_chart(fig_hist, use_container_width=True)

# ── AI ANALYSIS ───────────────────────────────────────
st.markdown("<div class='sec'>🤖 AI プロセス診断（Claude API）</div>",
            unsafe_allow_html=True)

if st.button("▶ AI診断を実行", type="primary"):
    if not api_key:
        st.warning("サイドバーにClaude API Keyを入力してください。")
    else:
        ss2 = fdf.groupby("stage").agg(
            avg_actual =("actual","mean"),
            avg_planned=("planned","mean"),
            rev_rate   =("revision",lambda x:(x>0).mean()),
            avg_rev    =("revision","mean"),
        ).round(2).reset_index()
        ss2 = ss2[ss2["stage"].isin(STAGES)]

        top5 = fdf.groupby("shot_id").agg(
            total_delay=("delay","sum"),
            project    =("project","first"),
            complexity =("complexity","first"),
        ).nlargest(5,"total_delay").reset_index()

        prompt = f"""あなたはCG制作プロダクションのプロセス改善コンサルタントです。
以下のデータを分析し、日本語で経営者向け診断レポートを作成してください。

【分析対象】{sel}
【ショット総数】{shots}件　【平均遅延】{avg_delay:.1f}日/ショット
【総リビジョン】{total_rev}回　【期限内完了率】{on_time:.0f}%

【工程】{" → ".join(STAGES)}

【工程別パフォーマンス】
{ss2.to_string(index=False)}

【遅延上位5ショット】
{top5.to_string(index=False)}

以下の構成で簡潔・具体的に答えてください：

## 🔍 最重要ボトルネック
（1〜2工程を具体的に。数値を使って）

## 📊 遅延の根本原因
（データから読み取れる構造的な問題を2〜3点）

## ✅ 即実行できる改善アクション
（3つ。各1〜2文で）

## ⚠️ 納期リスク評価
（高/中/低とその根拠を1〜2文で）"""

        with st.spinner("Claudeが分析中...（10〜20秒）"):
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type":"application/json",
                             "x-api-key":api_key,
                             "anthropic-version":"2023-06-01"},
                    json={"model":"claude-sonnet-4-6","max_tokens":1200,
                          "messages":[{"role":"user","content":prompt}]},
                    timeout=40
                )
                if resp.status_code==200:
                    st.markdown(
                        f"<div class='ai-box'>{resp.json()['content'][0]['text']}</div>",
                        unsafe_allow_html=True)
                else:
                    st.error(f"APIエラー {resp.status_code}: {resp.text}")
            except Exception as e:
                st.error(f"エラー: {e}")
else:
    st.markdown(f"""<div class='hint'>▶ ボタンを押すと Claudeがプロセスデータを分析し、
    <b>ボトルネック特定・根本原因・改善アクション・納期リスク評価</b>を自動生成します。
    サイドバーにClaude API Keyが必要です。</div>""", unsafe_allow_html=True)

st.divider()
st.caption("NeXT Diagnostics Demo v2.0　｜　スライド27工程準拠　｜　データはデモ用サンプルです")
