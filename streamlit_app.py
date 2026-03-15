import streamlit as st
import graphviz
import json
import os
import uuid
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# =========================
# 1. Member 類別
# =========================
class Member:
    def __init__(self, name, parent=None, side=None, is_clone=False):
        self.name = name
        self.parent = parent
        self.side = side
        self.is_clone = is_clone
        self.left = None
        self.right = None
        self.own = 0
        self.left_score = 0
        self.right_score = 0

    @property
    def commission(self):
        if self.name == "9999": return 0.0
        match_score = min(self.left_score, self.right_score)
        if match_score > 5000: match_score = 5000
        if match_score >= 125:
            return match_score * 0.2
        return 0.0

    def add_score(self, score):
        if self.name == "9999": return
        self.own += score
        self._check_clone()
        self._propagate(score)

    def _propagate(self, score):
        if not self.parent: return
        if self.side == "left":
            self.parent.left_score += score
        else:
            self.parent.right_score += score
        self.parent.own += score
        self.parent._propagate(score)

    def sub_score_sync(self, score):
        if self.name == "9999": return
        actual_sub = min(self.own, score)
        self.own -= actual_sub
        self._propagate_sub(actual_sub)

    def _propagate_sub(self, score):
        if not self.parent: return
        if self.side == "left":
            self.parent.left_score = max(0, self.parent.left_score - score)
        else:
            self.parent.right_score = max(0, self.parent.right_score - score)
        self.parent.own = max(0, self.parent.own - score)
        self.parent._propagate_sub(score)

    def _check_clone(self):
        if self.is_clone or self.name == "9999": return
        if self.own >= 200:
            if not self.left:
                new_left = Member(f"{self.name}_L", self, "left", True)
                self.left = new_left
                st.session_state.members[new_left.name] = new_left
            if not self.right:
                new_right = Member(f"{self.name}_R", self, "right", True)
                self.right = new_right
                st.session_state.members[new_right.name] = new_right

# =========================
# 2. 功能輔助函式
# =========================
def serialize_members(members_dict):
    return {name: {
        "name": m.name, "parent": m.parent.name if m.parent else None,
        "side": m.side, "is_clone": m.is_clone, "own": m.own,
        "left_score": m.left_score, "right_score": m.right_score
    } for name, m in members_dict.items()}

def deserialize_members(data):
    temp = {n: Member(i["name"], is_clone=i["is_clone"]) for n, i in data.items()}
    for n, m in temp.items():
        m.own, m.left_score, m.right_score, m.side = data[n]["own"], data[n]["left_score"], data[n]["right_score"], data[n]["side"]
    for n, i in data.items():
        if i["parent"] and i["parent"] in temp:
            c, p = temp[n], temp[i["parent"]]
            c.parent = p
            if c.side == "left": p.left = c
            else: p.right = c
    return temp

# --- Google Sheets 核心讀寫函數 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def save_to_cloud(filename):
    try:
        # 讀取現有所有資料
        existing_df = conn.read(ttl=0)
        
        # 準備新資料
        data_json = json.dumps(serialize_members(st.session_state.members), ensure_ascii=False)
        new_row = pd.DataFrame([{
            "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Filename": filename,
            "Data": data_json
        }])
        
        # 併入現有資料 (若 Filename 相同，之後讀取會抓最後一筆)
        updated_df = pd.concat([existing_df, new_row], ignore_index=True)
        conn.update(data=updated_df)
        st.toast(f"✅ 存檔 '{filename}' 已同步至雲端", icon="🚀")
    except Exception as e:
        st.error(f"儲存失敗: {e}")

def get_cloud_file_list():
    try:
        df = conn.read(ttl=0)
        if not df.empty and "Filename" in df.columns:
            return df["Filename"].unique().tolist()
    except:
        pass
    return []

def load_from_cloud(filename):
    try:
        df = conn.read(ttl=0)
        if not df.empty:
            # 找到該名稱最後一筆紀錄
            target_data = df[df["Filename"] == filename].iloc[-1]["Data"]
            return deserialize_members(json.loads(target_data))
    except Exception as e:
        st.error(f"讀取存檔失敗: {e}")
    return {"自己": Member("自己")}

def save_history():
    if "history" not in st.session_state: st.session_state.history = []
    st.session_state.history.append(serialize_members(st.session_state.members))
    if len(st.session_state.history) > 10: st.session_state.history.pop(0)

# =========================
# 3. 初始化
# =========================
if "members" not in st.session_state:
    # 預設載入雲端最後一筆，若無則初始化
    try:
        df_init = conn.read(ttl=0)
        if not df_init.empty:
            last_json = df_init.iloc[-1]["Data"]
            st.session_state.members = deserialize_members(json.loads(last_json))
        else:
            st.session_state.members = {"自己": Member("自己")}
    except:
        st.session_state.members = {"自己": Member("自己")}

if "selected" not in st.session_state:
    st.session_state.selected = "自己"
if "history" not in st.session_state:
    st.session_state.history = []

# =========================
# 4. 側邊控制
# =========================
st.sidebar.title("📁 系統管理")

if st.sidebar.button("🔙 Undo (復原上一步)", use_container_width=True):
    if st.session_state.history:
        st.session_state.members = deserialize_members(st.session_state.history.pop())
        st.rerun()

st.sidebar.divider()

member_keys = list(st.session_state.members.keys())
selected_name = st.sidebar.selectbox("選取操作節點", member_keys, index=member_keys.index(st.session_state.selected) if st.session_state.selected in member_keys else 0)
st.session_state.selected = selected_name
selected_node = st.session_state.members[selected_name]

tab1, tab2, tab3, tab4 = st.sidebar.tabs(["➕ 下線", "🔢 分數", "✏️ 編輯", "☁️ 雲端存檔"])

with tab1:
    c_name = st.text_input("下線名稱")
    c_side = st.radio("安置位置", ["left", "right"], horizontal=True)
    if st.button("確認建立"):
        if c_name and c_name not in st.session_state.members:
            if (c_side == "left" and not selected_node.left) or (c_side == "right" and not selected_node.right):
                save_history()
                child = Member(c_name, selected_node, c_side)
                st.session_state.members[c_name] = child
                if c_side == "left": selected_node.left = child
                else: selected_node.right = child
                st.rerun()

with tab2:
    st.subheader("業績調整")
    val = st.number_input("輸入分數值", min_value=0, step=10)
    if st.button("➕ 增加分數 (同步向上)", use_container_width=True):
        save_history()
        selected_node.add_score(val)
        st.rerun()
    
    col_sub1, col_sub2 = st.columns(2)
    with col_sub1:
        if st.button("➖ 單純減少", use_container_width=True):
            save_history()
            selected_node.own = max(0, selected_node.own - val)
            st.rerun()
    with col_sub2:
        if st.button("📉 同步扣除", use_container_width=True):
            save_history()
            selected_node.sub_score_sync(val)
            st.rerun()

with tab3:
    st.subheader("📝 名稱管理")
    new_name = st.text_input("修改名稱", value=selected_name)
    if st.button("確認更名"):
        if new_name and new_name != selected_name and new_name not in st.session_state.members:
            save_history()
            node = st.session_state.members.pop(selected_name)
            node.name = new_name
            st.session_state.members[new_name] = node
            st.session_state.selected = new_name
            st.rerun()

    st.divider()
    if st.button("❌ 帳戶作廢 (9999)", use_container_width=True):
        save_history()
        node_to_del = st.session_state.members.pop(selected_name)
        node_to_del.name = "9999"
        st.session_state.members["9999"] = node_to_del
        st.rerun()

with tab4:
    st.subheader("💾 建立新雲端存檔")
    save_name = st.text_input("存檔檔案名稱", value="預設進度")
    if st.button("📤 儲存至雲端", use_container_width=True, type="primary"):
        save_to_cloud(save_name)
    
    st.divider()
    
    st.subheader("📂 讀取雲端存檔")
    file_list = get_cloud_file_list()
    if file_list:
        target_file = st.selectbox("請選擇存檔", file_list)
        if st.button("🔄 載入所選進度", use_container_width=True):
            save_history()
            st.session_state.members = load_from_cloud(target_file)
            st.success(f"已成功載入: {target_file}")
            st.rerun()
    else:
        st.write("目前雲端尚無存檔資料。")

# =========================
# 5. 繪圖
# =========================
st.title("📊 直銷組織管理 (多檔雲端版)")

def draw_tree(root_member):
    dot = graphviz.Digraph()
    dot.attr(rankdir='TB', nodesep='0.5')
    dot.attr('node', shape='record', fontname='Microsoft JhengHei', style='filled')
    stack, visited = [root_member], set()
    while stack:
        curr = stack.pop()
        if curr in visited: continue
        visited.add(curr)
        
        if curr.name.startswith("9999"):
            fill, font, name_label = "#EF4444", "white", "已作廢 (9999)"
        else:
            fill = "#3B82F6" if curr.name == st.session_state.selected else ("#E2E8F0" if curr.is_clone else "#1E293B")
            font = "black" if curr.is_clone else "white"
            name_label = f"{curr.name}{' (店)' if curr.is_clone else ''}"

        label = (f"{{ {name_label} | Own: {curr.own} | "
                 f"{{ L: {curr.left_score} | R: {curr.right_score} }} | 💰 USD: ${curr.commission:.1f} }}")
        
        dot.node(str(id(curr)), label=label, fillcolor=fill, fontcolor=font)
        if curr.left: dot.edge(str(id(curr)), str(id(curr.left)), label="L"); stack.append(curr.left)
        if curr.right: dot.edge(str(id(curr)), str(id(curr.right)), label="R"); stack.append(curr.right)
    return dot

root = next((m for m in st.session_state.members.values() if m.parent is None), None)
if root:
    st.graphviz_chart(draw_tree(root), use_container_width=True)
