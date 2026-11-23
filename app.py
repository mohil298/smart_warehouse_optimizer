import streamlit as st
from database import (
    init_db, get_products, add_product, update_stock, delete_product,
    create_order, get_orders, update_order_status, dashboard_stats,
    save_delivery_assignments, clear_delivery_assignments, analytics_summary
)
from algorithms import (dijkstra, prioritize_orders, greedy_pick_plan,
                        greedy_vehicle_assignment, smart_delivery_assignment)

st.set_page_config(page_title="Smart Warehouse & Delivery", page_icon="📦", layout="wide")
init_db()

# Modern, responsive visual styling. No additional UI package is required.
st.markdown("""
<style>
:root { --brand:#2563eb; --ink:#172033; --muted:#667085; }
.block-container { padding-top: 1.5rem; padding-bottom: 2.5rem; max-width: 1500px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#101c35 0%,#172b4d 100%); }
[data-testid="stSidebar"] * { color: #f5f7fb !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding: .35rem .55rem; border-radius: 9px; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background: #ffffff18; }
.hero { padding: 1.35rem 1.55rem; border-radius: 18px; background: linear-gradient(115deg,#14213d,#2457a7 68%,#3979d8); color: white; margin-bottom: 1.15rem; box-shadow: 0 10px 28px #1d355722; }
.hero h1 { color:white; margin:0; font-size:1.8rem; letter-spacing:-.03em; }
.hero p { color:#dbeafe; margin:.35rem 0 0 0; }
.section-title { font-size:1.15rem; font-weight:700; color:#1d2939; margin:.7rem 0 .35rem; }
div[data-testid="stMetric"] { background:linear-gradient(180deg,#fff,#f8fbff); border:1px solid #e5eaf2; padding:14px 16px; border-radius:14px; box-shadow:0 3px 12px #10182808; }
.stButton>button, .stDownloadButton>button { border-radius:10px; font-weight:600; }
.stTabs [data-baseweb="tab-list"] { gap:8px; }
.stTabs [data-baseweb="tab"] { border-radius:9px 9px 0 0; padding:9px 15px; }
[data-testid="stDataFrame"] { border:1px solid #e7ebf2; border-radius:12px; overflow:hidden; }
div[data-testid="stAlert"] { border-radius:12px; }
</style>
""", unsafe_allow_html=True)

# Weighted undirected delivery network. Distances are illustrative kilometres.
EDGES = [
    ("Warehouse", "North Hub", 4), ("Warehouse", "East Hub", 6),
    ("Warehouse", "South Hub", 5), ("North Hub", "East Hub", 3),
    ("North Hub", "West Hub", 7), ("East Hub", "Central Hub", 2),
    ("South Hub", "Central Hub", 4), ("South Hub", "West Hub", 6),
    ("West Hub", "Central Hub", 3), ("Central Hub", "Customer Zone 1", 4),
    ("East Hub", "Customer Zone 2", 5), ("South Hub", "Customer Zone 3", 3),
    ("West Hub", "Customer Zone 4", 4)
]
GRAPH = {}
for a, b, distance in EDGES:
    GRAPH.setdefault(a, {})[b] = distance
    GRAPH.setdefault(b, {})[a] = distance
DESTINATIONS = ["Customer Zone 1", "Customer Zone 2", "Customer Zone 3", "Customer Zone 4"]


def trace_dijkstra(graph, start, destination):
    """Create teaching snapshots of Dijkstra's min-heap execution."""
    import heapq

    distances = {node: float("inf") for node in graph}
    previous = {}
    visited = set()
    distances[start] = 0
    heap = [(0, start)]
    steps = [{
        "current": None, "edge": None, "visited": set(),
        "distances": distances.copy(), "previous": previous.copy(),
        "message": f"Start at {start}. Its tentative distance is 0 km; all other nodes are infinity."
    }]

    while heap:
        current_distance, node = heapq.heappop(heap)
        if node in visited or current_distance != distances[node]:
            continue
        visited.add(node)
        steps.append({
            "current": node, "edge": None, "visited": visited.copy(),
            "distances": distances.copy(), "previous": previous.copy(),
            "message": f"Select {node} from the min-heap ({current_distance} km) and mark it visited."
        })
        if node == destination:
            break
        for neighbor, weight in graph[node].items():
            if neighbor in visited:
                continue
            candidate = current_distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(heap, (candidate, neighbor))
                message = f"Update {neighbor}: {current_distance} + {weight} = {candidate} km via {node}."
            else:
                message = f"Check {node} → {neighbor} ({weight} km): existing estimate for {neighbor} is better."
            steps.append({
                "current": node, "edge": (node, neighbor), "visited": visited.copy(),
                "distances": distances.copy(), "previous": previous.copy(),
                "message": message
            })

    path = []
    if distances[destination] != float("inf"):
        cursor = destination
        while cursor != start:
            path.append(cursor)
            cursor = previous[cursor]
        path.append(start)
        path.reverse()
    steps.append({
        "current": destination if path else None, "edge": None,
        "visited": visited.copy(), "distances": distances.copy(),
        "previous": previous.copy(),
        "message": "Destination reached. The highlighted path is the shortest route." if path else "No route exists to this destination."
    })
    return steps, path, distances[destination]


def draw_route_graph(graph, edges, snapshot, start, destination, final_path):
    """Render the fixed teaching network as an SVG with live algorithm states."""
    positions = {
        "Warehouse": (75, 205), "North Hub": (235, 75),
        "East Hub": (405, 115), "South Hub": (235, 340),
        "West Hub": (405, 300), "Central Hub": (590, 220),
        "Customer Zone 1": (790, 110), "Customer Zone 2": (790, 230),
        "Customer Zone 3": (405, 425), "Customer Zone 4": (590, 390)
    }
    visited = snapshot["visited"]
    current = snapshot["current"]
    current_edge = snapshot["edge"]
    distance_map = snapshot["distances"]
    path_edges = {frozenset((a, b)) for a, b in zip(final_path, final_path[1:])}
    pieces = ['<svg viewBox="0 0 880 490" role="img" aria-label="Dijkstra delivery network" style="width:100%;height:auto;background:#fbfcfe;border:1px solid #d9e0e8;border-radius:12px">']
    for a, b, weight in edges:
        x1, y1 = positions[a]
        x2, y2 = positions[b]
        pair = frozenset((a, b))
        on_path = bool(final_path) and pair in path_edges
        active = current_edge is not None and pair == frozenset(current_edge)
        color = "#16a34a" if on_path else ("#f59e0b" if active else "#b8c2cf")
        width = 6 if on_path else (5 if active else 2.5)
        pieces.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>')
        mx, my = (x1+x2)/2, (y1+y2)/2
        pieces.append(f'<rect x="{mx-13}" y="{my-12}" width="26" height="20" rx="6" fill="#ffffff" stroke="#d1d9e3"/><text x="{mx}" y="{my+3}" text-anchor="middle" font-size="12" font-weight="600" fill="#344054">{weight}</text>')
    for node, (x, y) in positions.items():
        if node == current:
            fill, stroke = "#fef3c7", "#d97706"
        elif node == start:
            fill, stroke = "#dcfce7", "#16a34a"
        elif node == destination:
            fill, stroke = "#fee2e2", "#dc2626"
        elif node in visited:
            fill, stroke = "#dbeafe", "#2563eb"
        else:
            fill, stroke = "#f3f4f6", "#8994a3"
        dist = distance_map.get(node, float("inf"))
        dist_text = "∞" if dist == float("inf") else f"{int(dist)} km"
        label = node.replace("Customer Zone ", "Zone ")
        pieces.append(f'<circle cx="{x}" cy="{y}" r="28" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
        pieces.append(f'<text x="{x}" y="{y+4}" text-anchor="middle" font-size="11" font-weight="700" fill="#172033">{dist_text}</text>')
        pieces.append(f'<text x="{x}" y="{y+47}" text-anchor="middle" font-size="13" font-weight="600" fill="#172033">{label}</text>')
    pieces.append('</svg>')
    return "".join(pieces)

st.markdown('<div class="hero"><h1>📦 Smart Warehouse & Delivery Suite</h1><p>Intelligent inventory control · Priority-aware dispatch · Shortest-path routing · Operational analytics</p></div>', unsafe_allow_html=True)
with st.sidebar:
    st.markdown("## WAREHOUSE OPS")
    page = st.radio("WORKSPACE", ["Dashboard", "Inventory", "Warehouse Layout", "Orders", "Smart Delivery Assignment", "Delivery Optimizer", "Advanced Analytics", "DSA Demonstration"])
    st.divider()
    st.caption("M.Tech DSA Project · Python 3.11")

if page == "Dashboard":
    st.subheader("Operations overview")
    st.caption("A live snapshot of stock health, order flow and fulfilment activity.")
    stats = dashboard_stats()
    cols = st.columns(5)
    labels = [("Products", stats["products"]), ("Units in stock", stats["units"]),
              ("Pending orders", stats["pending"]), ("Delivered", stats["completed"]),
              ("Low-stock items", stats["low"])]
    for col, (label, value) in zip(cols, labels):
        col.metric(label, value)
    st.subheader("Inventory snapshot")
    products = get_products()
    if products:
        st.dataframe([{k: p[k] for k in ["sku","name","category","quantity","reorder_level","location"]} for p in products], use_container_width=True, hide_index=True)
    low = [p for p in products if p["quantity"] <= p["reorder_level"]]
    if low:
        st.warning("Reorder required: " + ", ".join(p["name"] for p in low))
    else:
        st.success("All products are above their reorder levels.")

elif page == "Inventory":
    st.subheader("Inventory management")
    tab1, tab2, tab3 = st.tabs(["View / Search", "Add product", "Update / Delete"])
    with tab1:
        search = st.text_input("Search by SKU, product name or category")
        rows = get_products(search)
        st.dataframe(rows, use_container_width=True, hide_index=True)
    with tab2:
        with st.form("add_product_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            sku = c1.text_input("SKU (unique)", placeholder="SKU-2001")
            name = c2.text_input("Product name")
            category = c1.selectbox("Category", ["Electronics","Stationery","Lifestyle","Home","Other"])
            quantity = c2.number_input("Initial quantity", min_value=0, value=10, step=1)
            reorder = c1.number_input("Reorder level", min_value=0, value=5, step=1)
            location = c2.text_input("Shelf location", placeholder="A-03")
            submitted = st.form_submit_button("Add product")
            if submitted:
                try:
                    if not sku.strip() or not name.strip() or not location.strip():
                        st.error("SKU, product name and shelf location are required.")
                    else:
                        add_product(sku, name, category, int(quantity), int(reorder), location)
                        st.success("Product added.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Could not add product: {e}")
    with tab3:
        products = get_products()
        if products:
            options = {f'{p["sku"]} — {p["name"]} (ID {p["id"]})': p for p in products}
            selected_label = st.selectbox("Select product", list(options))
            selected = options[selected_label]
            new_qty = st.number_input("Set available quantity", min_value=0, value=int(selected["quantity"]), step=1)
            if st.button("Save stock quantity"):
                update_stock(selected["id"], int(new_qty))
                st.success("Stock updated.")
                st.rerun()
            if st.button("Delete selected product"):
                try:
                    delete_product(selected["id"])
                    st.success("Product deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


elif page == "Warehouse Layout":
    st.subheader("Interactive warehouse floor layout")
    st.caption("Select a shelf to inspect the products stored there. Shelf indicators are calculated from live inventory records.")

    products = get_products()

    def parse_shelf_code(code):
        code = str(code).strip().upper()
        if "-" in code:
            aisle, slot = code.split("-", 1)
            return aisle.strip() or "OTHER", slot.strip() or "01"
        return "OTHER", code or "01"

    locations = {}
    for product in products:
        locations.setdefault(product["location"].strip().upper(), []).append(product)

    aisle_names = sorted({"A", "B", "C", "D"} | {parse_shelf_code(loc)[0] for loc in locations})
    slot_names = {f"{i:02d}" for i in range(1, 7)}
    slot_names |= {parse_shelf_code(loc)[1] for loc in locations}
    ordered_slots = sorted(slot_names, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))

    total_shelves = len(aisle_names) * len(ordered_slots)
    occupied_shelves = len(locations)
    low_stock_count = sum(1 for p in products if p["quantity"] <= p["reorder_level"])

    metric_cols = st.columns(4)
    metric_cols[0].metric("Aisles", len(aisle_names))
    metric_cols[1].metric("Shelf positions", total_shelves)
    metric_cols[2].metric("Occupied locations", occupied_shelves)
    metric_cols[3].metric("Low-stock products", low_stock_count)

    st.markdown("**Shelf status legend**")
    legend1, legend2, legend3 = st.columns(3)
    legend1.success("🟢 In stock")
    legend2.warning("🟠 Reorder required")
    legend3.info("⚪ Empty shelf")

    if "selected_shelf" not in st.session_state:
        st.session_state["selected_shelf"] = "A-01"

    st.markdown("### Floor plan")
    st.caption("Aisles are shown as columns. Select any shelf card to view its inventory.")
    aisle_columns = st.columns(len(aisle_names))
    for aisle_index, aisle in enumerate(aisle_names):
        with aisle_columns[aisle_index]:
            st.markdown(f"**AISLE {aisle}**")
            for slot in ordered_slots:
                shelf_code = f"{aisle}-{slot}"
                shelf_products = locations.get(shelf_code, [])
                if not shelf_products:
                    icon, summary = "⚪", "Empty"
                elif any(p["quantity"] <= p["reorder_level"] for p in shelf_products):
                    icon, summary = "🟠", f'{len(shelf_products)} product(s) · low stock'
                else:
                    icon, summary = "🟢", f'{len(shelf_products)} product(s)'
                selected_marker = " ◀" if st.session_state["selected_shelf"] == shelf_code else ""
                if st.button(
                    f"{icon} {shelf_code}{selected_marker}\n{summary}",
                    key=f"warehouse_shelf_{aisle}_{slot}",
                    use_container_width=True
                ):
                    st.session_state["selected_shelf"] = shelf_code
                st.write("")

    selected_shelf = st.session_state["selected_shelf"]
    selected_products = locations.get(selected_shelf, [])
    st.divider()
    st.markdown(f"### Shelf details: `{selected_shelf}`")
    if selected_products:
        st.dataframe(
            [{
                "SKU": p["sku"],
                "Product": p["name"],
                "Category": p["category"],
                "Quantity": p["quantity"],
                "Reorder level": p["reorder_level"],
                "Status": "Reorder" if p["quantity"] <= p["reorder_level"] else "In stock"
            } for p in selected_products],
            use_container_width=True,
            hide_index=True
        )
        product_options = {
            f'{p["sku"]} — {p["name"]} (current: {p["quantity"]})': p
            for p in selected_products
        }
        chosen_product_label = st.selectbox("Choose product to adjust stock", list(product_options), key="layout_stock_product")
        chosen_product = product_options[chosen_product_label]
        revised_quantity = st.number_input(
            "New available quantity",
            min_value=0,
            value=int(chosen_product["quantity"]),
            step=1,
            key=f'layout_stock_qty_{chosen_product["id"]}'
        )
        if st.button("Update stock from warehouse layout", type="primary"):
            update_stock(chosen_product["id"], int(revised_quantity))
            st.success("Shelf inventory updated.")
            st.rerun()
    else:
        st.info("This shelf is currently empty. Add a product from Inventory and assign this shelf location.")
        st.write(f"To store a product here, use `{selected_shelf}` as its shelf location in Inventory → Add product.")

    with st.expander("How this layout works"):
        st.markdown("""
        - The layout reads product locations directly from the SQLite inventory database.
        - Green shelves contain products above their reorder levels.
        - Orange shelves contain at least one product at or below its reorder level.
        - White shelves have no products assigned.
        - Selecting a shelf displays its SKUs and lets the operator update stock.

        This is a logical warehouse floor plan for the academic prototype, not a measured architectural blueprint.
        """)


elif page == "Orders":
    st.subheader("Customer order management")
    products = get_products()
    if not products:
        st.info("Add inventory before creating an order.")
    else:
        with st.form("new_order_form", clear_on_submit=True):
            customer = st.text_input("Customer name")
            destination = st.selectbox("Delivery destination", DESTINATIONS)
            product_map = {f'{p["name"]} | {p["sku"]} | stock: {p["quantity"]}': p for p in products}
            product_label = st.selectbox("Product", list(product_map))
            qty = st.number_input("Quantity", min_value=1, value=1, step=1)
            priority_label = st.select_slider("Order priority", options=["Urgent","High","Normal","Low"], value="Normal")
            priority = {"Urgent":1,"High":2,"Normal":3,"Low":4}[priority_label]
            submit = st.form_submit_button("Place order")
            if submit:
                try:
                    if not customer.strip():
                        st.error("Enter a customer name.")
                    else:
                        create_order(customer, destination, product_map[product_label]["id"], int(qty), priority)
                        st.success("Order placed and stock reserved.")
                        st.rerun()
                except Exception as e:
                    st.error(str(e))
    st.divider()
    orders = get_orders()
    st.markdown("**Orders (urgent orders appear first)**")
    if orders:
        st.dataframe([{
            "Order": f'ORD-{o["id"]:04d}', "Customer": o["customer"], "Destination": o["destination"],
            "Product": o["product_name"], "Qty": o["quantity"],
            "Priority": {1:"Urgent",2:"High",3:"Normal",4:"Low"}.get(o["priority"], o["priority"]),
            "Status": o["status"], "Vehicle": o.get("assigned_vehicle") or "Not assigned",
            "Route (km)": o.get("route_km") if o.get("route_km") is not None else "—"
        } for o in orders], use_container_width=True, hide_index=True)
        pending = [o for o in orders if o["status"] in ("Pending","Processing")]
        if pending:
            order_map = {f'Order #{o["id"]} — {o["customer"]} — {o["status"]}': o for o in pending}
            chosen = st.selectbox("Select order to update", list(order_map))
            new_status = st.selectbox("New status", ["Processing","Dispatched","Delivered","Pending"])
            if st.button("Update order status"):
                update_order_status(order_map[chosen]["id"], new_status)
                st.success("Order status updated.")
                st.rerun()
    else:
        st.info("No orders yet.")

elif page == "Smart Delivery Assignment":
    st.subheader("Smart Delivery Assignment")
    st.caption("Automatically allocate unassigned orders to available vehicles using priority-aware First-Fit Decreasing and Dijkstra route estimates.")
    orders = get_orders()
    eligible = [o for o in orders if o["status"] != "Delivered" and not o.get("assigned_vehicle")]
    assigned_now = [o for o in orders if o.get("assigned_vehicle") and o["status"] != "Delivered"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Orders awaiting assignment", len(eligible))
    c2.metric("Already assigned", len(assigned_now))
    c3.metric("Delivered orders", sum(o["status"] == "Delivered" for o in orders))
    st.info("Capacity is measured in **order units** (the quantity field), because this prototype does not yet store physical parcel weight or dimensions. Route distances use the sample road network.")
    with st.form("smart_assignment_form"):
        a, b = st.columns(2)
        vehicle_count = a.number_input("Available vehicles", min_value=1, max_value=30, value=3, step=1)
        capacity_units = b.number_input("Capacity per vehicle (order units)", min_value=1, max_value=500, value=20, step=1)
        run_assignment = st.form_submit_button("🚚 Generate smart assignments", type="primary", use_container_width=True)
    if run_assignment:
        planned, unassigned = smart_delivery_assignment(
            eligible, int(vehicle_count), int(capacity_units),
            lambda zone: dijkstra(GRAPH, "Warehouse", zone)[0]
        )
        if planned:
            save_delivery_assignments({name: data["orders"] for name, data in planned.items()})
            st.session_state["last_assignment_unassigned"] = unassigned
            st.success(f"Successfully assigned {sum(len(v['orders']) for v in planned.values())} order(s) across {len(planned)} vehicle(s).")
            st.rerun()
        else:
            st.warning("No orders could be assigned. Check whether unassigned orders exist and vehicle capacity is sufficient.")
            st.session_state["last_assignment_unassigned"] = unassigned
    if st.button("Clear active assignments", disabled=not assigned_now):
        clear_delivery_assignments()
        st.success("Active assignments cleared. Delivered orders are not changed.")
        st.rerun()
    st.markdown("### Current vehicle plan")
    if assigned_now:
        by_vehicle = {}
        for order in assigned_now:
            by_vehicle.setdefault(order["assigned_vehicle"], []).append(order)
        for vehicle, vehicle_orders in sorted(by_vehicle.items()):
            total_load = sum(int(o["quantity"]) for o in vehicle_orders)
            route_total = sum(float(o["route_km"] or 0) for o in vehicle_orders)
            with st.expander(f"{vehicle}  ·  {len(vehicle_orders)} order(s)  ·  {total_load} capacity units  ·  {route_total:.1f} route-km", expanded=True):
                st.dataframe([{
                    "Order": f'ORD-{o["id"]:04d}', "Customer": o["customer"], "Destination": o["destination"],
                    "Product": o["product_name"], "Units": o["quantity"],
                    "Priority": {1:"Urgent",2:"High",3:"Normal",4:"Low"}.get(o["priority"], o["priority"]),
                    "Route estimate (km)": o["route_km"]
                } for o in vehicle_orders], use_container_width=True, hide_index=True)
                st.progress(min(total_load / max(int(capacity_units), 1), 1.0), text=f"Illustrative capacity utilisation: {total_load} / {int(capacity_units)} units")
    else:
        st.info("No active vehicle assignments yet. Generate assignments above after placing customer orders.")
    unassigned = st.session_state.get("last_assignment_unassigned", [])
    if unassigned:
        st.markdown("### Orders not assigned")
        st.dataframe([{"Order ID": o["id"], "Customer": o["customer"], "Units": o["quantity"], "Reason": o["reason"]} for o in unassigned], use_container_width=True, hide_index=True)
    with st.expander("How the assignment algorithm works"):
        st.markdown("""
        1. Ignore delivered orders and orders that already have a vehicle.
        2. Sort remaining orders by urgency (Urgent → High → Normal → Low), then larger loads first.
        3. Place each order in the first vehicle with enough remaining capacity (First-Fit Decreasing-style heuristic).
        4. Calculate each assigned order's warehouse-to-destination shortest distance using Dijkstra.
        5. Save the vehicle, route estimate and assignment timestamp in SQLite.

        This is a practical heuristic for the academic prototype; it is not a global optimum and does not model traffic, service times or multi-stop road sequencing.
        """)

elif page == "Advanced Analytics":
    st.subheader("Advanced Analytics")
    st.caption("Explore warehouse health, order fulfilment, demand patterns and delivery workload using your local SQLite data.")
    stats = dashboard_stats()
    analytics = analytics_summary()
    products = get_products()
    orders = get_orders()
    delivered_rate = analytics["delivered_rate"]
    pending_count = sum(o["status"] == "Pending" for o in orders)
    processing_count = sum(o["status"] in ("Processing", "Dispatched") for o in orders)
    total_value_units = sum(int(p["quantity"]) for p in products)
    m = st.columns(5)
    m[0].metric("Total orders", analytics["total_orders"])
    m[1].metric("Delivery completion", f"{delivered_rate}%")
    m[2].metric("Pending", pending_count)
    m[3].metric("Assigned active", analytics["assigned"])
    m[4].metric("Inventory units", total_value_units)
    tab1, tab2, tab3 = st.tabs(["📈 Order performance", "📦 Inventory intelligence", "🧭 Delivery insights"])
    with tab1:
        left, right = st.columns(2)
        with left:
            st.markdown("**Orders by status**")
            status_data = [{"Status": r["status"], "Orders": r["total"]} for r in analytics["status"]]
            if status_data:
                st.bar_chart(status_data, x="Status", y="Orders", use_container_width=True)
            else:
                st.info("No order data yet.")
        with right:
            st.markdown("**Orders by priority**")
            priority_names = {1:"Urgent",2:"High",3:"Normal",4:"Low"}
            priority_data = [{"Priority": priority_names.get(r["priority"], str(r["priority"])), "Orders": r["total"]} for r in analytics["priority"]]
            if priority_data:
                st.bar_chart(priority_data, x="Priority", y="Orders", use_container_width=True)
            else:
                st.info("Priority analysis will appear after orders are created.")
        st.markdown("**Daily order creation trend**")
        if analytics["daily"]:
            st.line_chart([{"Date": r["day"], "Orders": r["orders"]} for r in analytics["daily"]], x="Date", y="Orders", use_container_width=True)
        else:
            st.info("No daily trend available yet.")
        st.dataframe([{"Status": r["status"], "Order count": r["total"]} for r in analytics["status"]], use_container_width=True, hide_index=True)
    with tab2:
        left, right = st.columns(2)
        with left:
            st.markdown("**Available units by category**")
            if analytics["category"]:
                st.bar_chart([{"Category": r["category"], "Units": r["units"] or 0} for r in analytics["category"]], x="Category", y="Units", use_container_width=True)
            else:
                st.info("No inventory data available.")
        with right:
            st.markdown("**Stock health**")
            low_items = [p for p in products if p["quantity"] <= p["reorder_level"]]
            healthy_items = [p for p in products if p["quantity"] > p["reorder_level"]]
            st.metric("Healthy SKUs", len(healthy_items))
            st.metric("Reorder alerts", len(low_items))
            st.metric("Total SKUs", len(products))
        if low_items:
            st.warning("Items at or below reorder level")
            st.dataframe([{"SKU": p["sku"], "Product": p["name"], "Stock": p["quantity"], "Reorder at": p["reorder_level"], "Shelf": p["location"], "Shortfall": max(0, p["reorder_level"]-p["quantity"])} for p in low_items], use_container_width=True, hide_index=True)
        else:
            st.success("No products currently need replenishment.")
        st.markdown("**Inventory register**")
        st.dataframe([{"SKU": p["sku"], "Product": p["name"], "Category": p["category"], "Available units": p["quantity"], "Reorder level": p["reorder_level"], "Location": p["location"]} for p in products], use_container_width=True, hide_index=True)
    with tab3:
        left, right = st.columns(2)
        with left:
            st.markdown("**Orders by destination**")
            if analytics["destination"]:
                st.bar_chart([{"Destination": r["destination"], "Orders": r["total"]} for r in analytics["destination"]], x="Destination", y="Orders", use_container_width=True)
            else:
                st.info("Destination analysis will appear after orders are placed.")
        with right:
            st.markdown("**Dispatch coverage**")
            active_orders = [o for o in orders if o["status"] != "Delivered"]
            assigned_orders = [o for o in active_orders if o.get("assigned_vehicle")]
            coverage = round(len(assigned_orders) / len(active_orders) * 100, 1) if active_orders else 0
            st.metric("Active orders with a vehicle", f"{coverage}%")
            st.metric("Active unassigned orders", len(active_orders)-len(assigned_orders))
            st.metric("Unique vehicles in use", len({o["assigned_vehicle"] for o in assigned_orders}))
        if assigned_orders:
            st.markdown("**Vehicle workload**")
            vehicle_loads = {}
            for order in assigned_orders:
                vehicle_loads[order["assigned_vehicle"]] = vehicle_loads.get(order["assigned_vehicle"], 0) + int(order["quantity"])
            st.bar_chart([{"Vehicle": v, "Order units": units} for v, units in sorted(vehicle_loads.items())], x="Vehicle", y="Order units", use_container_width=True)
        st.caption("Analytics are calculated from orders and inventory stored in your local SQLite database. Route distances and capacity units are prototype estimates.")

elif page == "Delivery Optimizer":
    st.subheader("Dijkstra shortest-route visualizer")
    st.caption("Step through the min-heap algorithm and watch tentative distances change across the delivery network.")
    destination = st.selectbox("Choose customer destination", DESTINATIONS, key="route_destination")
    trace, path, distance = trace_dijkstra(GRAPH, "Warehouse", destination)

    if st.session_state.get("trace_destination") != destination:
        st.session_state["trace_destination"] = destination
        st.session_state["route_step"] = 0

    max_step = len(trace) - 1
    if "route_step" not in st.session_state:
        st.session_state["route_step"] = 0
    st.session_state["route_step"] = min(st.session_state["route_step"], max_step)

    control_a, control_b, control_c, control_d = st.columns([1, 1, 1, 2])
    if control_a.button("⏮ Reset", use_container_width=True):
        st.session_state["route_step"] = 0
    if control_b.button("◀ Previous", disabled=st.session_state["route_step"] == 0, use_container_width=True):
        st.session_state["route_step"] -= 1
    if control_c.button("Next ▶", disabled=st.session_state["route_step"] >= max_step, use_container_width=True):
        st.session_state["route_step"] += 1
    control_d.caption("Use Next to animate one algorithm event at a time.")

    step_index = st.slider("Animation step", min_value=0, max_value=max_step, key="route_step")
    snapshot = trace[step_index]
    st.progress((step_index + 1) / len(trace), text=f"Step {step_index + 1} of {len(trace)}")
    st.info(snapshot["message"])
    st.markdown(draw_route_graph(GRAPH, EDGES, snapshot, "Warehouse", destination, path if step_index == max_step else []), unsafe_allow_html=True)

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Best known distance", "∞" if snapshot["distances"][destination] == float("inf") else f'{snapshot["distances"][destination]} km')
    metric2.metric("Visited locations", len(snapshot["visited"]))
    metric3.metric("Algorithm events", len(trace) - 1)

    with st.expander("Tentative distances at this step", expanded=True):
        distance_rows = [{"Location": node, "Tentative distance": "∞" if value == float("inf") else f"{value} km", "Status": "Visited" if node in snapshot["visited"] else ("Currently processing" if node == snapshot["current"] else "Unvisited")} for node, value in snapshot["distances"].items()]
        st.dataframe(distance_rows, use_container_width=True, hide_index=True)

    if step_index == max_step and path:
        st.success(f"Shortest route: {' → '.join(path)} | Total distance: {distance} km")
    elif path:
        st.caption("Green edges show the final shortest path for reference; orange highlights the edge being examined in the current step.")
    st.markdown("**Network connections and edge weights (km)**")
    st.dataframe([{"From":a,"To":b,"Distance (km)":w} for a,b,w in EDGES], use_container_width=True, hide_index=True)
    st.caption("All distances are illustrative sample data, not live GPS or road traffic measurements.")

elif page == "DSA Demonstration":
    st.subheader("DSA algorithms in this project")
    st.markdown("""
    **1. Hash Map / Dictionary — Inventory lookup**  
    Product records are retrieved by their unique database ID or SKU search index. Average hash lookup complexity is **O(1)**.

    **2. Priority Queue / Min-Heap — Order scheduling**  
    Urgent orders are assigned smaller priority numbers. Heap insertion and removal take **O(log n)**; viewing the next order is **O(1)**.

    **3. Graph + Dijkstra — Delivery route optimization**  
    Locations are vertices and roads are weighted edges. With an adjacency list and binary heap, complexity is **O((V + E) log V)**.

    **4. Greedy picking — Shelf ordering**  
    Requested products are sorted by aisle/shelf location to create an easy picking sequence. Sorting takes **O(n log n)**.

    **5. First-Fit Decreasing + priority sorting — Smart delivery assignment**  
    Orders are sorted by urgency and load, then fitted into vehicles with available capacity. This is a heuristic, not a guaranteed optimal packing solution. Each order's route estimate is calculated using Dijkstra.

    **6. SQL Aggregation — Advanced analytics**  
    SQLite `GROUP BY`, `SUM`, `COUNT` and date grouping produce order, inventory and dispatch summaries without requiring Pandas or NumPy.
    """)
    orders = [o for o in get_orders() if o["status"] == "Pending"]
    if orders:
        st.markdown("**Priority queue output (pending orders)**")
        ordered = prioritize_orders(orders)
        st.dataframe([{"Order ID":o["id"],"Customer":o["customer"],"Priority":o["priority"],"Product":o["product_name"]} for o in ordered], use_container_width=True, hide_index=True)
    products = get_products()
    if products:
        st.markdown("**Greedy shelf-picking sequence (sample: all products)**")
        plan = greedy_pick_plan(products)
        st.write(" → ".join(f'{p["location"]} ({p["name"]})' for p in plan))
    st.markdown("**Vehicle allocation example**")
    sample_deliveries = [{"order":"ORD-1","weight":8},{"order":"ORD-2","weight":5},{"order":"ORD-3","weight":4},{"order":"ORD-4","weight":3}]
    capacity = st.number_input("Vehicle capacity (kg)", min_value=5, max_value=100, value=10)
    groups = greedy_vehicle_assignment(sample_deliveries, float(capacity))
    for i, group in enumerate(groups, 1):
        st.write(f"Vehicle {i}: " + ", ".join(f'{d["order"]} ({d["weight"]} kg)' for d in group))
        st.caption(f"Total load: {sum(d['weight'] for d in group)} kg")
