import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from itertools import combinations
from collections import Counter
import datetime

# Import existing fetchers from your services
from services.tally_sales_view import fetch_sales_register
from services.tally_stock_view import fetch_tally_stock_data


def render_advanced_analysis_page():
    st.title("🧠 Commercial Intelligence & Inventory Optimization")
    st.caption(
        "Advanced customer retention, Pareto inventory prioritization, cross-sell discovery, and predictive procurement.")

    # ---------------------------------------------------------
    # 1. LOAD & NORMALIZE DATA
    # ---------------------------------------------------------
    v_df, i_df = fetch_sales_register()
    stock_df, error = fetch_tally_stock_data()

    if v_df.empty or i_df.empty or stock_df.empty:
        st.warning("⚠️ Insufficient data to perform analysis. Ensure sales registers and stock summaries are synced.")
        return

    v_df["voucher_date"] = pd.to_datetime(v_df["voucher_date"])
    i_df["billed_qty_numeric"] = pd.to_numeric(i_df["billed_qty_numeric"], errors="coerce").fillna(0.0)
    i_df["item_name"] = i_df["item_name"].astype(str).str.strip().str.upper()

    stock_df["Item Name"] = stock_df["Item Name"].astype(str).str.strip().str.upper()
    stock_df["Stock Qty"] = pd.to_numeric(stock_df["Stock Qty"], errors="coerce").fillna(0.0)

    # Filter non-zero items and merge with vouchers
    active_items = i_df[i_df["billed_qty_numeric"] > 0].copy()
    master_sales = pd.merge(
        active_items,
        v_df[["voucher_id", "party_name", "voucher_date", "voucher_number"]],
        on="voucher_id",
        how="inner"
    )

    # ---------------------------------------------------------
    # 2. RENDER TABS
    # ---------------------------------------------------------
    tab_rfm, tab_abc, tab_basket, tab_procurement, tab_seasonality, tab_matrix = st.tabs([
        "🚨 At-Risk Customers",
        "📊 ABC Inventory",
        "💡 Cross-Sell",
        "🛒 Procurement Engine",
        "📈 Seasonality Trends",
        "🤝 Party-Item Matrix"
    ])

    # ==========================================
    # TAB 1: AT-RISK CUSTOMERS (RFM)
    # ==========================================
    with tab_rfm:
        st.subheader("Customer Health & Churn Risk")
        today = pd.to_datetime(datetime.date.today())

        rfm = master_sales.groupby("party_name").agg(
            last_purchase=("voucher_date", "max"),
            frequency=("voucher_id", "nunique"),
            total_volume=("billed_qty_numeric", "sum")
        ).reset_index()

        rfm["days_inactive"] = (today - rfm["last_purchase"]).dt.days

        c1, c2 = st.columns(2)
        dormant_threshold = c1.slider("Dormancy Threshold (Days Inactive):", 15, 180, 45, 5)
        vip_min_volume = c2.number_input("VIP Volume Threshold (Min Quantity):",
                                         value=float(rfm["total_volume"].quantile(0.75)))

        def segment_party(row):
            if row["days_inactive"] > dormant_threshold and row["total_volume"] >= vip_min_volume:
                return "🔥 Critical Risk (High-Value Churn)"
            elif row["days_inactive"] > dormant_threshold:
                return "⚠️ Inactive Low-Value"
            elif row["total_volume"] >= vip_min_volume:
                return "⭐ Active VIP"
            else:
                return "✅ Active Regular"

        rfm["health_status"] = rfm.apply(segment_party, axis=1)

        color_map = {
            "🔥 Critical Risk (High-Value Churn)": "#EF553B",
            "⭐ Active VIP": "#00CC96",
            "⚠️ Inactive Low-Value": "#FFA15A",
            "✅ Active Regular": "#636EFA"
        }

        fig_rfm = px.scatter(
            rfm, x="days_inactive", y="frequency", size="total_volume",
            color="health_status", hover_name="party_name", color_discrete_map=color_map,
            labels={"days_inactive": "Days Since Last Order", "frequency": "Order Frequency",
                    "total_volume": "Total Qty"},
            title="Customer Retention Matrix (Bubble Size = Total Volume)"
        )
        fig_rfm.add_vline(x=dormant_threshold, line_dash="dash", line_color="grey")
        st.plotly_chart(fig_rfm, use_container_width=True)

        critical_parties = rfm[rfm["health_status"] == "🔥 Critical Risk (High-Value Churn)"].sort_values(
            by="total_volume", ascending=False)
        if not critical_parties.empty:
            st.error(f"⚠️ {len(critical_parties)} High-volume customers require immediate outreach:")
            st.dataframe(
                critical_parties[["party_name", "days_inactive", "frequency", "total_volume", "last_purchase"]],
                use_container_width=True, hide_index=True)
        else:
            st.success("No high-value customers are currently past the dormancy threshold.")

    # ==========================================
    # TAB 2: ABC INVENTORY (PARETO)
    # ==========================================
    with tab_abc:
        st.subheader("Pareto Inventory Classification (80/20 Rule)")

        sku_volume = master_sales.groupby("item_name")["billed_qty_numeric"].sum().reset_index()
        sku_volume = sku_volume.sort_values(by="billed_qty_numeric", ascending=False).reset_index(drop=True)

        total_units = sku_volume["billed_qty_numeric"].sum()
        sku_volume["cumulative_qty"] = sku_volume["billed_qty_numeric"].cumsum()
        sku_volume["cumulative_pct"] = (sku_volume["cumulative_qty"] / total_units) * 100

        def assign_abc(pct):
            if pct <= 80.0:
                return "Class A"
            elif pct <= 95.0:
                return "Class B"
            else:
                return "Class C"

        sku_volume["abc_class"] = sku_volume["cumulative_pct"].apply(assign_abc)

        top_30 = sku_volume.head(30)
        fig_pareto = go.Figure()
        fig_pareto.add_trace(
            go.Bar(x=top_30["item_name"], y=top_30["billed_qty_numeric"], name="Volume", marker_color="#636EFA"))
        fig_pareto.add_trace(
            go.Scatter(x=top_30["item_name"], y=top_30["cumulative_pct"], name="Cumulative %", yaxis="y2",
                       mode="lines+markers", line=dict(color="#EF553B", width=2)))
        fig_pareto.update_layout(
            title="Top 30 Products: Dispatch Volume & Cumulative Curve",
            yaxis=dict(title="Units Sold"),
            yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0, 105]),
            xaxis=dict(tickangle=45), legend=dict(x=0.8, y=1.1, orientation="h")
        )
        st.plotly_chart(fig_pareto, use_container_width=True)

    # ==========================================
    # TAB 3: CROSS-SELLING (MARKET BASKET)
    # ==========================================
    with tab_basket:
        st.subheader("Market Basket Cross-Selling Engine")

        vch_groups = master_sales.groupby("voucher_id")["item_name"].unique()
        pair_counts = Counter()
        for items in vch_groups:
            if len(items) > 1:
                for pair in combinations(sorted(items), 2):
                    pair_counts[pair] += 1

        if pair_counts:
            basket_df = pd.DataFrame([
                {"Product A": p[0], "Product B": p[1], "Together_Count": c} for p, c in pair_counts.items()
            ]).sort_values(by="Together_Count", ascending=False)

            b1, b2 = st.columns([1, 2])
            with b1:
                target_product = st.selectbox("Inspect Upsell for:", sorted(master_sales["item_name"].unique()))
                min_support = st.number_input("Min Joint Orders:", min_value=1, value=2)

            filtered_pairs = basket_df[
                ((basket_df["Product A"] == target_product) | (basket_df["Product B"] == target_product)) &
                (basket_df["Together_Count"] >= min_support)
                ].copy()

            filtered_pairs["Recommended_Upsell"] = filtered_pairs.apply(
                lambda r: r["Product B"] if r["Product A"] == target_product else r["Product A"], axis=1
            )

            with b2:
                if not filtered_pairs.empty:
                    fig_upsell = px.bar(
                        filtered_pairs.head(10), x="Together_Count", y="Recommended_Upsell", orientation="h",
                        title=f"Frequently Ordered with '{target_product}'"
                    )
                    fig_upsell.update_layout(yaxis={"categoryorder": "total ascending"})
                    st.plotly_chart(fig_upsell, use_container_width=True)
                else:
                    st.info(f"No strong bundling found for '{target_product}'.")
        else:
            st.info("Invoices only contain single items.")

    # ==========================================
    # TAB 4: SMART PROCUREMENT ENGINE
    # ==========================================
    with tab_procurement:
        st.subheader("Intelligent Replenishment Generator")

        master_sales["month_year"] = master_sales["voucher_date"].dt.to_period("M")
        monthly_series = master_sales.groupby(["item_name", "month_year"])["billed_qty_numeric"].sum().reset_index()
        avg_monthly = monthly_series.groupby("item_name")["billed_qty_numeric"].mean().reset_index()
        avg_monthly.rename(columns={"billed_qty_numeric": "Monthly_Runrate"}, inplace=True)

        merged_ops = pd.merge(stock_df[["Item Name", "Stock Qty", "Unit"]], avg_monthly, left_on="Item Name",
                              right_on="item_name", how="left")
        merged_ops = pd.merge(merged_ops, sku_volume[["item_name", "abc_class"]], on="item_name", how="left")
        merged_ops["Monthly_Runrate"] = merged_ops["Monthly_Runrate"].fillna(0.0)
        merged_ops["abc_class"] = merged_ops["abc_class"].fillna("Class C")

        col_buf1, col_buf2, col_buf3 = st.columns(3)
        buf_a = col_buf1.slider("Class A Safety Buffer (%)", 10, 100, 30, 5) / 100.0
        buf_b = col_buf2.slider("Class B Safety Buffer (%)", 5, 50, 15, 5) / 100.0
        buf_c = col_buf3.slider("Class C Safety Buffer (%)", 0, 20, 5, 5) / 100.0

        def get_buffer(abc):
            if abc == "Class A":
                return buf_a
            elif abc == "Class B":
                return buf_b
            return buf_c

        merged_ops["applied_buffer"] = merged_ops["abc_class"].apply(get_buffer)
        merged_ops["Target_Stock"] = merged_ops["Monthly_Runrate"] * (1.0 + merged_ops["applied_buffer"])
        merged_ops["Order_Required"] = merged_ops["Target_Stock"] - merged_ops["Stock Qty"]

        order_sheet = merged_ops[(merged_ops["Order_Required"] > 0) & (merged_ops["Monthly_Runrate"] > 0)].copy()
        order_sheet = order_sheet.sort_values(by=["abc_class", "Order_Required"], ascending=[True, False])

        if not order_sheet.empty:
            st.error(f"📋 Purchase Order Required: {len(order_sheet)} items below targets.")
            st.dataframe(order_sheet[["Item Name", "abc_class", "Stock Qty", "Monthly_Runrate", "Target_Stock",
                                      "Order_Required", "Unit"]], use_container_width=True, hide_index=True)
        else:
            st.success("✅ Healthy Inventory: All items are sufficiently stocked.")

    # ==========================================
    # TAB 5: SEASONALITY TRENDS
    # ==========================================
    with tab_seasonality:
        st.subheader("📈 Demand Velocity & Seasonality")

        unique_items_list = sorted(master_sales["item_name"].dropna().unique())
        target_item = st.selectbox("Select Product for Trend Analysis:", unique_items_list)

        trend_data = master_sales[master_sales["item_name"] == target_item].copy()
        trend_data["Month"] = trend_data["voucher_date"].dt.to_period("M").dt.to_timestamp()
        monthly_trend = trend_data.groupby("Month")["billed_qty_numeric"].sum().reset_index()

        if not monthly_trend.empty:
            fig_trend = px.area(
                monthly_trend, x="Month", y="billed_qty_numeric", title=f"Monthly Sales Velocity: {target_item}",
                labels={"Month": "Date", "billed_qty_numeric": "Total Units Sold"}, markers=True
            )
            fig_trend.update_traces(line_color="#00CC96", fillcolor="rgba(0, 204, 150, 0.2)")
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info(f"No historical trend data available for {target_item}.")

    # ==========================================
    # TAB 6: PARTY-ITEM MATRIX (WHO BUYS WHAT)
    # ==========================================
    with tab_matrix:
        st.subheader("🤝 Who Buys What (Party-Item Matrix)")

        top_20_parties = master_sales.groupby("party_name")["billed_qty_numeric"].sum().nlargest(20).index
        matrix_data = master_sales[master_sales["party_name"].isin(top_20_parties)]

        heatmap = pd.pivot_table(
            matrix_data, values="billed_qty_numeric", index="party_name", columns="item_name", aggfunc="sum",
            fill_value=0
        )

        heatmap = heatmap.loc[:, (heatmap != 0).any(axis=0)]

        st.caption("Total volume purchased by your Top 20 customers across active products.")
        st.dataframe(heatmap.style.background_gradient(cmap="Blues"), use_container_width=True)