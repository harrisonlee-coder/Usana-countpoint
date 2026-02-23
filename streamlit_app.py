import streamlit as st
import graphviz
import json
import os
import glob


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
        # 若帳戶已作廢，不計算獎金
        if self.name == "9999": return 0.0
        match_score = min(self.left_score, self.right_score)
        if match_score > 5000: match_score = 5000
        if match_score >= 125:
            return match_score * 0.2
        return 0.0

    def add_score(self, score):
        if self.name == "9999": return  # 作廢帳戶不可加分
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
SAVE_DIR = "mlm_saves"
if not os.path.exists(SAVE_DIR): os.makedirs(SAVE_DIR)


def save_history():
    if "history" not in st.session_state: st.session_state.history = []
    st.session_state.history.append(serialize_members(st.session_state.members))
    if len(st.session_state.history) > 10: st.session_state.history.pop(0)


def serialize_members(members_dict):
    return {name: {
        "name": m.name, "parent": m.parent.name if m.parent else None,
        "side": m.side, "is_clone": m.is_clone, "own": m.own,
        "left_score": m.left_score, "right_score": m.right_score
    } for name, m in members_dict.items()}


def deserialize_members(data):
    temp = {n: Member(i["name"], is_clone=i["is_clone"]) for n, i in data.items()}
    for n, m in temp.items():
        m.own, m.left_score, m.right_score, m.side = data[n]["own"], data[n]["left_score"], data[n]["right_score"], \
        data[n]["side"]
    for n, i in data.items():
        if i["parent"] and i["parent"] in temp:
            c, p = temp[n], temp[i["parent"]]
            c.parent = p
            if c.side == "left":
                p.left = c
            else:
                p.right = c
    return temp


# =========================
# 3. 初始化
# =========================
if "members" not in st.session_state:
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

# 選取與編輯
member_keys = list(st.session_state.members.keys())
selected_name = st.sidebar.selectbox("選取操作節點", member_keys, index=member_keys.index(
    st.session_state.selected) if st.session_state.selected in member_keys else 0)
st.session_state.selected = selected_name
selected_node = st.session_state.members[selected_name]

tab1, tab2, tab3, tab4 = st.sidebar.tabs(["➕ 下線", "💰 加分", "✏️ 編輯", "💾 存檔"])

with tab1:
    c_name = st.text_input("下線名稱")
    c_side = st.radio("安置位置", ["left", "right"], horizontal=True)
    if st.button("確認建立"):
        if c_name and c_name not in st.session_state.members:
            if (c_side == "left" and not selected_node.left) or (c_side == "right" and not selected_node.right):
                save_history()
                child = Member(c_name, selected_node, c_side)
                st.session_state.members[c_name] = child
                if c_side == "left":
                    selected_node.left = child
                else:
                    selected_node.right = child
                st.rerun()

with tab2:
    val = st.number_input("輸入分數", min_value=0, step=10)
    if st.button("執行加分"):
        save_history()
        selected_node.add_score(val)
        st.rerun()

with tab3:
    st.subheader("📝 修改名稱")
    new_name = st.text_input("新名稱", value=selected_name)
    if st.button("確認更名"):
        if new_name and new_name != selected_name and new_name not in st.session_state.members:
            save_history()
            # 更新字典 Key
            node = st.session_state.members.pop(selected_name)
            node.name = new_name
            st.session_state.members[new_name] = node
            st.session_state.selected = new_name
            st.rerun()

    st.divider()
    st.subheader("⚠️ 帳戶作廢")
    if st.button("❌ 刪除 (更名為 9999)"):
        save_history()
        # 處理本人
        node_to_del = st.session_state.members.pop(selected_name)
        node_to_del.name = "9999"
        st.session_state.members["9999"] = node_to_del

        # 處理分身 (店)
        clones = [m for m in st.session_state.members.values() if m.parent == node_to_del and m.is_clone]
        for c in clones:
            st.session_state.members.pop(c.name)
            c.name = "9999"
            # 為了避免 Key 重複，這裡我們使用 9999_L 這種標記，或統一叫 9999
            # 由於字典 Key 唯一，我們加上隨機 ID 或索引
            import uuid

            unique_key = f"9999_{str(uuid.uuid4())[:4]}"
            st.session_state.members[unique_key] = c

        st.session_state.selected = "9999"
        st.rerun()

    st.divider()
    if st.sidebar.button("🧹 一鍵清空所有分數"):
        save_history()
        for m in st.session_state.members.values():
            m.own = m.left_score = m.right_score = 0
        st.rerun()

with tab4:
    s_name = st.text_input("存檔檔案名稱", value="預設存檔")
    if st.button("💾 儲存"):
        data = serialize_members(st.session_state.members)
        with open(os.path.join(SAVE_DIR, f"{s_name}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        st.success("已儲存")

    files = [os.path.basename(f).replace(".json", "") for f in glob.glob(os.path.join(SAVE_DIR, "*.json"))]
    if files:
        l_target = st.selectbox("讀取存檔", files)
        if st.button("📂 載入"):
            save_history()
            with open(os.path.join(SAVE_DIR, f"{l_target}.json"), "r", encoding="utf-8") as f:
                st.session_state.members = deserialize_members(json.load(f))
            st.rerun()

# =========================
# 5. 繪圖
# =========================
st.title("📊 直銷組織對碰系統 (帳戶管理版)")


def draw_tree(root_member):
    dot = graphviz.Digraph()
    dot.attr(rankdir='TB', nodesep='0.5')
    dot.attr('node', shape='record', fontname='Microsoft JhengHei', style='filled')
    stack, visited = [root_member], set()
    while stack:
        curr = stack.pop()
        if curr in visited: continue
        visited.add(curr)

        # 顏色邏輯：9999 為紅色
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