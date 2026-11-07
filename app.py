import sqlite3
import json
from pathlib import Path
from datetime import date
import streamlit as st
import pandas as pd

DB_PATH = Path(__file__).with_name("my_league.db")
MY_TEAM = "FC Barcelona"
INITIAL_SEASON = "2026/27"

DEFAULT_TEAMS = [
    "Athletic Club", "Atlético de Madrid", "CA Osasuna", "Celta",
    "Deportivo Alavés", "Elche CF", "FC Barcelona", "Getafe CF",
    "Levante UD", "Málaga CF", "R. Racing Club", "Rayo Vallecano",
    "RC Deportivo", "RCD Espanyol", "Real Betis", "Real Madrid",
    "Real Sociedad", "Sevilla FC", "Valencia CF", "Villarreal CF",
]

st.set_page_config(page_title="マイリーグ管理", page_icon="⚽", layout="wide")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT '進行中',
                started_at TEXT NOT NULL,
                ended_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_date TEXT NOT NULL,
                opponent_id INTEGER NOT NULL,
                barca_goals INTEGER NOT NULL,
                opponent_goals INTEGER NOT NULL,
                season_id INTEGER,
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
        con.execute("""
            CREATE TABLE IF NOT EXISTS season_archives (
                season_id INTEGER PRIMARY KEY,
                standings_json TEXT NOT NULL,
                scorers_json TEXT NOT NULL,
                assists_json TEXT NOT NULL,
                finalized_at TEXT NOT NULL,
                FOREIGN KEY(season_id) REFERENCES seasons(id)
            )
        """)

        # 既存データベースにシーズン機能を追加するための移行処理
        columns = [r[1] for r in con.execute("PRAGMA table_info(matches)").fetchall()]
        if "season_id" not in columns:
            con.execute("ALTER TABLE matches ADD COLUMN season_id INTEGER")

        if con.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0:
            con.executemany("INSERT INTO teams(name) VALUES (?)", [(t,) for t in DEFAULT_TEAMS])

        if con.execute("SELECT COUNT(*) FROM seasons").fetchone()[0] == 0:
            con.execute(
                "INSERT INTO seasons(name, status, started_at) VALUES (?, '進行中', ?)",
                (INITIAL_SEASON, date.today().isoformat())
            )

        current_row = con.execute(
            "SELECT id FROM seasons WHERE status='進行中' ORDER BY id DESC LIMIT 1"
        ).fetchone()

        # これまで登録した試合は、初回作成した進行中シーズンに引き継ぐ
        if current_row:
            con.execute(
                "UPDATE matches SET season_id=? WHERE season_id IS NULL",
                (current_row[0],)
            )


def get_teams():
    with connect() as con:
        return pd.read_sql_query("SELECT id, name FROM teams ORDER BY name", con)


def get_seasons():
    with connect() as con:
        return pd.read_sql_query(
            "SELECT id, name, status, started_at, ended_at FROM seasons ORDER BY id DESC",
            con
        )


def get_matches(season_id):
    with connect() as con:
        return pd.read_sql_query("""
            SELECT m.id, m.match_date, t.name AS opponent,
                   m.barca_goals, m.opponent_goals
            FROM matches m
            JOIN teams t ON t.id=m.opponent_id
            WHERE m.season_id=?
            ORDER BY m.match_date DESC, m.id DESC
        """, con, params=(int(season_id),))


def get_events(season_id):
    with connect() as con:
        return pd.read_sql_query("""
            SELECT e.match_id, e.scorer, COALESCE(e.assister, '') AS assister
            FROM goal_events e
            JOIN matches m ON m.id=e.match_id
            WHERE m.season_id=?
        """, con, params=(int(season_id),))


def build_standings(teams, matches):
    rows = []
    for _, team in teams.iterrows():
        name = team["name"]
        played = wins = draws = losses = gf = ga = 0

        if name == MY_TEAM:
            relevant = matches
            for _, m in relevant.iterrows():
                played += 1
                gf += int(m["barca_goals"])
                ga += int(m["opponent_goals"])
                if m["barca_goals"] > m["opponent_goals"]:
                    wins += 1
                elif m["barca_goals"] == m["opponent_goals"]:
                    draws += 1
                else:
                    losses += 1
        else:
            relevant = matches[matches["opponent"] == name]
            for _, m in relevant.iterrows():
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
            "得点": gf, "失点": ga, "得失点差": gf-ga, "勝点": wins*3+draws
        })

    frame = pd.DataFrame(rows)
    return frame.sort_values(
        ["勝点", "得失点差", "得点"], ascending=False
    ).reset_index(drop=True)


def make_ranking(events, column, label):
    if events.empty:
        return pd.DataFrame(columns=["順位", "選手名", label])
    data = events[events[column].astype(str).str.strip() != ""]
    if data.empty:
        return pd.DataFrame(columns=["順位", "選手名", label])
    ranking = data.groupby(column).size().reset_index(name=label)
    ranking = ranking.sort_values([label, column], ascending=[False, True]).head(20)
    ranking = ranking.reset_index(drop=True)
    ranking.insert(0, "順位", range(1, len(ranking)+1))
    return ranking.rename(columns={column: "選手名"})


def archive_season(season_id, teams, matches, events):
    standings = build_standings(teams, matches)
    scorers = make_ranking(events, "scorer", "得点数")
    assists = make_ranking(events, "assister", "アシスト数")
    with connect() as con:
        con.execute("""
            INSERT OR REPLACE INTO season_archives
            (season_id, standings_json, scorers_json, assists_json, finalized_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            int(season_id),
            standings.to_json(orient="records", force_ascii=False),
            scorers.to_json(orient="records", force_ascii=False),
            assists.to_json(orient="records", force_ascii=False),
            date.today().isoformat()
        ))
        con.execute(
            "UPDATE seasons SET status='終了', ended_at=? WHERE id=?",
            (date.today().isoformat(), int(season_id))
        )


def load_archive(season_id):
    with connect() as con:
        row = con.execute("""
            SELECT standings_json, scorers_json, assists_json, finalized_at
            FROM season_archives WHERE season_id=?
        """, (int(season_id),)).fetchone()
    if not row:
        return None
    return {
        "standings": pd.read_json(row[0]),
        "scorers": pd.read_json(row[1]),
        "assists": pd.read_json(row[2]),
        "finalized_at": row[3]
    }


init_db()
teams = get_teams()
seasons = get_seasons()

st.markdown("""
<style>
.stApp {background:linear-gradient(145deg,#10131d 0%,#171d2b 55%,#111827 100%);}
.block-container {padding-top:1.4rem;padding-bottom:2.5rem;max-width:1100px;}
.hero {background:linear-gradient(115deg,#142b58 0%,#263f7b 52%,#7a1734 100%);
border:1px solid rgba(255,255,255,.13);border-radius:18px;padding:22px 24px;margin-bottom:18px;}
.hero-kicker {color:#d9e5ff;font-size:12px;letter-spacing:2px;font-weight:700;}
.hero-title {font-size:clamp(24px,5vw,38px);font-weight:900;margin:3px 0;color:white;}
.hero-sub {color:#e7eaf3;font-size:13px;}
.stButton>button {border-radius:10px;font-weight:700;min-height:42px;}
[data-testid="stDataFrame"] {border:1px solid rgba(255,255,255,.10);border-radius:12px;overflow:hidden;}
div[data-testid="stMetric"] {background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);padding:12px;border-radius:12px;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
 <div class="hero-kicker">eFOOTBALL · MY LEAGUE</div>
 <div class="hero-title">⚽ マイリーグ管理</div>
 <div class="hero-sub">FC Barcelona · LALIGA EA SPORTS</div>
</div>
""", unsafe_allow_html=True)

# シーズン選択
season_options = {int(r["id"]): r["name"] for _, r in seasons.iterrows()}
default_season_id = int(seasons.iloc[0]["id"])
selected_season_id = st.sidebar.selectbox(
    "📅 表示するシーズン",
    list(season_options.keys()),
    index=0,
    format_func=lambda x: season_options[x]
)
selected_season = seasons[seasons["id"] == selected_season_id].iloc[0]
is_active = selected_season["status"] == "進行中"

page = st.sidebar.radio("📋 メニュー", [
    "ホーム", "順位表", "試合登録", "得点ランキング",
    "アシストランキング", "試合履歴", "シーズン管理", "チーム管理"
])
st.sidebar.caption(f"現在表示中：{selected_season['name']}（{selected_season['status']}）")
st.sidebar.markdown("---")
st.sidebar.caption("⚽ FC Barcelona のマイリーグ成績を管理しよう！")

matches = get_matches(selected_season_id)
events = get_events(selected_season_id)
archive = load_archive(selected_season_id)

st.markdown(f"### {selected_season['name']} シーズン")

if not is_active:
    st.info("このシーズンは終了済みです。記録の閲覧のみ可能です。")

# ホーム
if page == "ホーム":
    st.subheader("📊 シーズン成績")
    total = len(matches)
    wins = int((matches["barca_goals"] > matches["opponent_goals"]).sum()) if total else 0
    draws = int((matches["barca_goals"] == matches["opponent_goals"]).sum()) if total else 0
    losses = total-wins-draws
    gf = int(matches["barca_goals"].sum()) if total else 0
    ga = int(matches["opponent_goals"].sum()) if total else 0
    cols = st.columns(4)
    for col, label, value in zip(cols, ["試合数","勝・分・敗","総得点","総失点"],
                                 [total,f"{wins} - {draws} - {losses}",gf,ga]):
        col.metric(label, value)

    c1, c2 = st.columns(2)
    c1.metric("得失点差", gf-ga)
    c2.metric("勝点", wins*3+draws)

    st.markdown("### 🕒 最近の試合")
    if matches.empty:
        st.info("まだ試合結果がありません。「試合登録」から登録しよう！")
    else:
        recent = matches.head(5).copy()
        recent["結果"] = recent.apply(
            lambda r: "勝利" if r.barca_goals>r.opponent_goals
            else ("引き分け" if r.barca_goals==r.opponent_goals else "敗北"), axis=1)
        recent["スコア"] = recent["barca_goals"].astype(str)+" - "+recent["opponent_goals"].astype(str)
        st.dataframe(recent[["match_date","opponent","スコア","結果"]].rename(
            columns={"match_date":"試合日","opponent":"対戦相手"}),
            use_container_width=True, hide_index=True)

    st.caption("※順位表はBarcelonaとの対戦結果のみを反映しています。他クラブ同士の試合は含みません。")

# 順位表
elif page == "順位表":
    st.subheader("🏆 ラ・リーガ順位表")
    st.caption("Barcelonaが登録した対戦結果をもとに集計しています。他クラブ同士の試合は未入力です。")
    table = archive["standings"] if archive else build_standings(teams, matches)
    table.insert(0, "順位", range(1, len(table)+1))
    st.dataframe(table, use_container_width=True, hide_index=True)

# 試合登録
elif page == "試合登録":
    st.subheader("⚽ 試合結果を登録")
    if not is_active:
        st.warning("終了したシーズンには試合を追加できません。新シーズンを開始してください。")
    else:
        opponents = teams[teams["name"] != MY_TEAM]
        with st.form("match_form"):
            match_date = st.date_input("📅 試合日", value=date.today())
            opponent_name = st.selectbox("対戦相手", opponents["name"].tolist())
            c1,c2 = st.columns(2)
            barca_goals = c1.number_input("🔵🔴 Barcelonaの得点",0,30,0,1)
            opponent_goals = c2.number_input("相手チームの得点",0,30,0,1)
            st.markdown("#### ⚽ 得点者・アシスト")
            st.caption("Barcelonaの得点数と同じ人数分入力。アシストがない場合は空欄でOK。")
            scorers, assisters = [], []
            for i in range(int(barca_goals)):
                a,b = st.columns(2)
                scorers.append(a.text_input(f"{i+1}点目の得点者", key=f"scorer_{selected_season_id}_{i}"))
                assisters.append(b.text_input(f"{i+1}点目のアシスト", key=f"assist_{selected_season_id}_{i}"))
            submitted = st.form_submit_button("💾 試合結果を保存", use_container_width=True)
            if submitted:
                if any(not s.strip() for s in scorers):
                    st.error("得点者をすべて入力してください。")
                else:
                    opponent_id = int(opponents.loc[opponents["name"]==opponent_name,"id"].iloc[0])
                    with connect() as con:
                        cur = con.execute("""INSERT INTO matches
                            (match_date,opponent_id,barca_goals,opponent_goals,season_id)
                            VALUES (?,?,?,?,?)""",
                            (match_date.isoformat(),opponent_id,int(barca_goals),int(opponent_goals),int(selected_season_id)))
                        match_id = cur.lastrowid
                        con.executemany("""INSERT INTO goal_events(match_id,scorer,assister)
                            VALUES (?,?,?)""",
                            [(match_id,s.strip(),a.strip() or None) for s,a in zip(scorers,assisters)])
                    st.success("試合結果を保存しました！")
                    st.rerun()

# ランキング：シーズン終了時に確定したものを表示
elif page in ["得点ランキング","アシストランキング"]:
    is_scorer = page == "得点ランキング"
    st.subheader("👑 得点ランキング TOP20" if is_scorer else "🎯 アシストランキング TOP20")
    if not archive:
        st.info("ランキングはシーズン終了時に確定します。シーズン終了後にTOP20が表示されます。")
    else:
        ranking = archive["scorers"] if is_scorer else archive["assists"]
        if ranking.empty:
            st.info("このシーズンの記録はありません。")
        else:
            st.dataframe(ranking, use_container_width=True, hide_index=True)

# 試合履歴
elif page == "試合履歴":
    st.subheader("📋 試合履歴")
    if matches.empty:
        st.info("登録済みの試合はありません。")
    else:
        st.dataframe(matches.rename(columns={
            "match_date":"試合日","opponent":"対戦相手",
            "barca_goals":"Barcelona得点","opponent_goals":"相手得点"
        })[["id","試合日","対戦相手","Barcelona得点","相手得点"]],
            use_container_width=True, hide_index=True)
        if is_active:
            st.markdown("#### 🗑️ 試合の削除")
            selected_match = st.selectbox("削除する試合ID", matches["id"].tolist())
            if st.button("選択した試合を削除", type="secondary"):
                with connect() as con:
                    con.execute("DELETE FROM goal_events WHERE match_id=?",(int(selected_match),))
                    con.execute("DELETE FROM matches WHERE id=?",(int(selected_match),))
                st.success("試合を削除しました。")
                st.rerun()

# シーズン管理
elif page == "シーズン管理":
    st.subheader("📅 シーズン管理")
    st.markdown("#### シーズン一覧")
    st.dataframe(seasons.rename(columns={
        "name":"シーズン","status":"状態","started_at":"開始日","ended_at":"終了日"
    })[["シーズン","状態","開始日","終了日"]], use_container_width=True, hide_index=True)

    if is_active:
        st.markdown("#### 🏁 シーズンを終了")
        st.warning("終了すると、このシーズンの順位表・得点ランキング・アシストランキングが確定し、試合の追加・削除ができなくなります。")
        confirm = st.checkbox("このシーズンを終了して成績を確定する")
        if st.button("シーズン終了・成績確定", type="primary", disabled=not confirm):
            archive_season(selected_season_id, teams, matches, events)
            st.success("シーズンを終了し、最終成績を保存しました！")
            st.rerun()
    else:
        st.info("過去シーズンの成績は保存されています。")

    st.markdown("#### ➕ 新しいシーズンを開始")
    active_exists = not seasons[seasons["status"]=="進行中"].empty
    if active_exists:
        st.info("進行中のシーズンがあるため、新しいシーズンは開始できません。先に現在のシーズンを終了してください。")
    else:
        with st.form("new_season_form"):
            new_season_name = st.text_input("新しいシーズン名", placeholder="例：2027/28")
            start_new = st.form_submit_button("新シーズンを開始")
            if start_new:
                name = new_season_name.strip()
                if not name:
                    st.error("シーズン名を入力してください。")
                else:
                    try:
                        with connect() as con:
                            con.execute("INSERT INTO seasons(name,status,started_at) VALUES (?,'進行中',?)",
                                        (name,date.today().isoformat()))
                        st.success(f"{name} シーズンを開始しました！")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("そのシーズン名はすでに登録されています。")

# チーム管理
elif page == "チーム管理":
    st.subheader("🛠️ チーム管理")
    st.caption("チームの追加・削除ができます。試合記録に使われているチームは削除できません。")
    st.dataframe(teams[["name"]].rename(columns={"name":"チーム名"}),
                 use_container_width=True, hide_index=True)
    st.markdown("#### ➕ チームを追加")
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
                        con.execute("INSERT INTO teams(name) VALUES (?)",(name,))
                    st.success(f"{name} を追加しました。")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("そのチームはすでに登録されています。")
    st.markdown("#### 🗑️ チームを削除")
    removable = teams[teams["name"] != MY_TEAM]
    if not removable.empty:
        selected_team = st.selectbox("削除するチーム",removable["name"].tolist())
        if st.button("選択したチームを削除",type="secondary"):
            tid = int(removable.loc[removable["name"]==selected_team,"id"].iloc[0])
            with connect() as con:
                used = con.execute("SELECT COUNT(*) FROM matches WHERE opponent_id=?",(tid,)).fetchone()[0]
                if used:
                    st.error("このチームとの試合記録があるため削除できません。")
                else:
                    con.execute("DELETE FROM teams WHERE id=?",(tid,))
                    st.success("チームを削除しました。")
                    st.rerun()

st.markdown("---")
st.caption("⚽ 個人用マイリーグ管理アプリ｜eFootballのゲームデータとは自動連携しません。")
