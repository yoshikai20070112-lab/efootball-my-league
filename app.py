import sqlite3
from pathlib import Path
from datetime import date
import streamlit as st
import pandas as pd

DB_PATH = Path(__file__).with_name("my_league.db")
MY_TEAM = "FC Barcelona"
DEFAULT_TEAMS = [
    "Athletic Club", "Atlético de Madrid", "CA Osasuna", "Celta",
    "Deportivo Alavés", "Elche CF", "FC Barcelona", "Getafe CF",
    "Levante UD", "Málaga CF", "R. Racing Club", "Rayo Vallecano",
    "RC Deportivo", "RCD Espanyol", "Real Betis", "Real Madrid",
    "Real Sociedad", "Sevilla FC", "Valencia CF", "Villarreal CF",
]

st.set_page_config(page_title="My League Manager", page_icon="⚽", layout="wide")

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_date TEXT NOT NULL,
                opponent_id INTEGER NOT NULL,
                barca_goals INTEGER NOT NULL,
                opponent_goals INTEGER NOT NULL,
                FOREIGN KEY(opponent_id) REFERENCES teams(id)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS goal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                scorer TEXT NOT NULL,
                assister TEXT,
                FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE
            )
        """)
        count = con.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        if count == 0:
            con.executemany("INSERT INTO teams(name) VALUES (?)", [(t,) for t in DEFAULT_TEAMS])

def get_teams():
    with connect() as con:
        return pd.read_sql_query("SELECT id, name FROM teams ORDER BY name", con)

def get_matches():
    with connect() as con:
        return pd.read_sql_query("""
            SELECT m.id, m.match_date, t.name AS opponent,
                   m.barca_goals, m.opponent_goals
            FROM matches m JOIN teams t ON t.id = m.opponent_id
            ORDER BY m.match_date DESC, m.id DESC
        """, con)

def get_events():
    with connect() as con:
        return pd.read_sql_query("""
            SELECT e.match_id, e.scorer, COALESCE(e.assister, '') AS assister
            FROM goal_events e
        """, con)

def build_standings(teams, matches):
    rows = []
    for _, team in teams.iterrows():
        name = team["name"]
        played = wins = draws = losses = gf = ga = 0
        for _, m in matches.iterrows():
            if m["opponent"] != name:
                continue
            played += 1
            gf += int(m["opponent_goals"])
            ga += int(m["barca_goals"])
            if m["opponent_goals"] > m["barca_goals"]:
                wins += 1
            elif m["opponent_goals"] == m["barca_goals"]:
                draws += 1
            else:
                losses += 1
        rows.append({
            "チーム": name, "試合": played, "勝": wins, "分": draws, "敗": losses,
            "得点": gf, "失点": ga, "得失点": gf-ga, "勝点": wins*3+draws
        })
    # Barcelona's figures are the inverse of its opponents' results.
    b = next((r for r in rows if r["チーム"] == MY_TEAM), None)
    if b:
        b["試合"] = sum(1 for _, m in matches.iterrows())
        b["勝"] = sum(1 for _, m in matches.iterrows() if m["barca_goals"] > m["opponent_goals"])
        b["分"] = sum(1 for _, m in matches.iterrows() if m["barca_goals"] == m["opponent_goals"])
        b["敗"] = sum(1 for _, m in matches.iterrows() if m["barca_goals"] < m["opponent_goals"])
        b["得点"] = int(matches["barca_goals"].sum()) if not matches.empty else 0
        b["失点"] = int(matches["opponent_goals"].sum()) if not matches.empty else 0
        b["得失点"] = b["得点"] - b["失点"]
        b["勝点"] = b["勝"]*3 + b["分"]
    frame = pd.DataFrame(rows)
    return frame.sort_values(["勝点", "得失点", "得点"], ascending=False).reset_index(drop=True)

def style_table(df):
    return df.style

init_db()
teams = get_teams()
matches = get_matches()
events = get_events()

st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: linear-gradient(145deg, #10131d 0%, #171d2b 55%, #111827 100%); }
.block-container { padding-top: 1.4rem; padding-bottom: 2.5rem; max-width: 1100px; }
h1, h2, h3 { letter-spacing: .2px; }
.hero {
  background: linear-gradient(115deg, #142b58 0%, #263f7b 52%, #7a1734 100%);
  border: 1px solid rgba(255,255,255,.13); border-radius: 18px;
  padding: 22px 24px; margin-bottom: 18px;
}
.hero-kicker { color: #d9e5ff; font-size: 12px; letter-spacing: 2px; font-weight: 700; }
.hero-title { font-size: clamp(24px, 5vw, 38px); font-weight: 900; margin: 3px 0; color: white; }
.hero-sub { color: #e7eaf3; font-size: 13px; }
.metric-card {
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.10);
  padding: 14px 16px; border-radius: 14px; min-height: 90px;
}
.metric-label { color: #aebbd1; font-size: 12px; }
.metric-value { color: white; font-size: 27px; font-weight: 800; }
.small-note { color: #aebbd1; font-size: 12px; }
div[data-testid="stMetric"] { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); padding: 12px; border-radius: 12px; }
.stButton > button { border-radius: 10px; font-weight: 700; min-height: 42px; }
[data-testid="stDataFrame"] { border: 1px solid rgba(255,255,255,.10); border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-kicker">eFOOTBALL · MY LEAGUE</div>
  <div class="hero-title">⚽ MY LEAGUE MANAGER</div>
  <div class="hero-sub">FC Barcelona · LALIGA EA SPORTS · 2026/27</div>
</div>
""", unsafe_allow_html=True)

page = st.sidebar.radio("MENU", ["HOME", "STANDINGS", "MATCH INPUT", "SCORERS", "ASSISTS", "MATCH HISTORY", "TEAMS"])
st.sidebar.markdown("---")
st.sidebar.caption("データはこのアプリのSQLiteデータベースに保存されます。")

if page == "HOME":
    st.subheader("SEASON OVERVIEW")
    total = len(matches)
    wins = int((matches["barca_goals"] > matches["opponent_goals"]).sum()) if total else 0
    draws = int((matches["barca_goals"] == matches["opponent_goals"]).sum()) if total else 0
    losses = total - wins - draws
    gf = int(matches["barca_goals"].sum()) if total else 0
    ga = int(matches["opponent_goals"].sum()) if total else 0
    cols = st.columns(4)
    for col, label, value in zip(cols, ["MATCHES", "W-D-L", "GOALS FOR", "GOALS AGAINST"],
                                 [total, f"{wins}-{draws}-{losses}", gf, ga]):
        with col:
            st.metric(label, value)
    st.markdown("### 最近の試合")
    if matches.empty:
        st.info("まだ試合結果がありません。「MATCH INPUT」から最初の試合を登録しよう！")
    else:
        recent = matches.head(5).copy()
        recent["結果"] = recent.apply(
            lambda r: "WIN" if r.barca_goals > r.opponent_goals else ("DRAW" if r.barca_goals == r.opponent_goals else "LOSS"), axis=1)
        recent["スコア"] = recent["barca_goals"].astype(str) + " - " + recent["opponent_goals"].astype(str)
        st.dataframe(recent[["match_date", "opponent", "スコア", "結果"]].rename(
            columns={"match_date":"日付", "opponent":"対戦相手"}), use_container_width=True, hide_index=True)
    if total:
        st.markdown("### シーズン成績")
        c1, c2 = st.columns(2)
        c1.metric("勝率", f"{wins/total*100:.1f}%")
        c2.metric("1試合平均得点", f"{gf/total:.2f}")

elif page == "STANDINGS":
    st.subheader("🏆 LALIGA STANDINGS")
    st.caption("入力したFC Barcelonaの試合結果をもとに集計します。他クラブ同士の試合は未入力のため、全20クラブの完全な順位表ではありません。")
    table = build_standings(teams, matches)
    table.insert(0, "順位", range(1, len(table)+1))
    st.dataframe(table, use_container_width=True, hide_index=True)

elif page == "MATCH INPUT":
    st.subheader("⚽ 試合結果を登録")
    opponents = teams[teams["name"] != MY_TEAM]
    if opponents.empty:
        st.warning("対戦相手チームを先に登録してください。")
    else:
        with st.form("match_form"):
            match_date = st.date_input("試合日", value=date.today())
            opponent_name = st.selectbox("対戦相手", opponents["name"].tolist())
            c1, c2 = st.columns(2)
            with c1:
                barca_goals = st.number_input("Barcelonaの得点", min_value=0, max_value=30, value=0, step=1)
            with c2:
                opponent_goals = st.number_input("相手の得点", min_value=0, max_value=30, value=0, step=1)
            st.markdown("#### 得点者・アシスト")
            st.caption("Barcelonaの得点数と同じ人数分、得点者を入力してください。アシストがない場合は空欄でOK。")
            scorer_names, assister_names = [], []
            for i in range(int(barca_goals)):
                a, b = st.columns(2)
                with a:
                    scorer_names.append(st.text_input(f"{i+1}点目の得点者", key=f"scorer_{i}"))
                with b:
                    assister_names.append(st.text_input(f"{i+1}点目のアシスト", key=f"assist_{i}"))
            submitted = st.form_submit_button("試合結果を保存", use_container_width=True)
            if submitted:
                if any(not s.strip() for s in scorer_names):
                    st.error("得点者をすべて入力してください。")
                else:
                    opponent_id = int(opponents.loc[opponents["name"] == opponent_name, "id"].iloc[0])
                    with connect() as con:
                        cur = con.execute(
                            "INSERT INTO matches(match_date, opponent_id, barca_goals, opponent_goals) VALUES (?, ?, ?, ?)",
                            (match_date.isoformat(), opponent_id, int(barca_goals), int(opponent_goals)))
                        match_id = cur.lastrowid
                        con.executemany(
                            "INSERT INTO goal_events(match_id, scorer, assister) VALUES (?, ?, ?)",
                            [(match_id, s.strip(), a.strip() or None) for s, a in zip(scorer_names, assister_names)])
                    st.success("試合結果を保存しました！")
                    st.rerun()

elif page in ["SCORERS", "ASSISTS"]:
    is_scorer = page == "SCORERS"
    st.subheader("👑 " + ("TOP SCORERS" if is_scorer else "🎯 TOP ASSISTS"))
    if events.empty:
        st.info("まだ選手データがありません。試合結果を登録するとランキングが作成されます。")
    else:
        column = "scorer" if is_scorer else "assister"
        data = events[events[column].astype(str).str.strip() != ""]
        ranking = data.groupby(column).size().reset_index(name="回数")
        ranking = ranking.sort_values(["回数", column], ascending=[False, True]).reset_index(drop=True)
        ranking.insert(0, "順位", range(1, len(ranking)+1))
        ranking = ranking.rename(columns={column:"選手", "回数":"得点" if is_scorer else "アシスト"})
        st.dataframe(ranking, use_container_width=True, hide_index=True)

elif page == "MATCH HISTORY":
    st.subheader("📋 MATCH HISTORY")
    if matches.empty:
        st.info("登録済みの試合はありません。")
    else:
        st.dataframe(matches.rename(columns={
            "match_date":"日付", "opponent":"対戦相手",
            "barca_goals":"Barcelona", "opponent_goals":"相手"
        })[["id", "日付", "対戦相手", "Barcelona", "相手"]], use_container_width=True, hide_index=True)
        st.markdown("#### 試合の削除")
        match_ids = matches["id"].tolist()
        selected = st.selectbox("削除する試合ID", match_ids)
        if st.button("選択した試合を削除", type="secondary"):
            with connect() as con:
                con.execute("DELETE FROM goal_events WHERE match_id = ?", (int(selected),))
                con.execute("DELETE FROM matches WHERE id = ?", (int(selected),))
            st.success("試合を削除しました。")
            st.rerun()

elif page == "TEAMS":
    st.subheader("🛠️ チーム管理")
    st.caption("2026/27シーズンのラ・リーガ20クラブを初期登録しています。追加・削除もできます。")
    st.dataframe(teams[["name"]].rename(columns={"name":"チーム"}), use_container_width=True, hide_index=True)
    with st.form("add_team"):
        new_team = st.text_input("追加するチーム名")
        add = st.form_submit_button("チームを追加")
        if add:
            name = new_team.strip()
            if not name:
                st.error("チーム名を入力してください。")
            else:
                try:
                    with connect() as con:
                        con.execute("INSERT INTO teams(name) VALUES (?)", (name,))
                    st.success(f"{name} を追加しました。")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("そのチームはすでに登録されています。")
    st.markdown("#### チームを削除")
    removable = teams[teams["name"] != MY_TEAM]
    if not removable.empty:
        selected_team = st.selectbox("削除するチーム", removable["name"].tolist())
        if st.button("選択したチームを削除", type="secondary"):
            tid = int(removable.loc[removable["name"] == selected_team, "id"].iloc[0])
            with connect() as con:
                used = con.execute("SELECT COUNT(*) FROM matches WHERE opponent_id = ?", (tid,)).fetchone()[0]
                if used:
                    st.error("このチームとの試合記録があるため削除できません。先に試合記録を削除してください。")
                else:
                    con.execute("DELETE FROM teams WHERE id = ?", (tid,))
                    st.success("チームを削除しました。")
                    st.rerun()

st.markdown("---")
st.caption("Unofficial personal tracker · eFootballのゲームデータとは自動連携しません。")
