"""Double-sided market network topology.

Extracted from week8_pf_auction.py (render_network_topology, tab 2) on
2026-08-12. The CSS, session state, sidebar and footer shared with the
other DC network experiments live in experiments/_kit/dc_network.py.
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from typing import Any, Dict, List, Optional  # noqa: F401
import networkx as nx
import warnings
warnings.filterwarnings('ignore')

from experiments._kit import dc_network

STATE_GROUP = "dc_network"


def _update_bus_configuration(edited_buses_df):
    """Update bus configuration and regenerate generators/retailers lists"""
    try:
        # Update network bus configuration
        for i, row in edited_buses_df.iterrows():
            bus_idx = int(row['Bus']) - 1  # Convert to 0-based index
            
            # Update bus properties
            st.session_state.network['buses'][bus_idx]['type'] = row['Type']
            st.session_state.network['buses'][bus_idx]['v_magnitude'] = row['V_nom']
            
            # Parse generators and retailers from comma-separated strings
            generators = []
            if row['Generators'] and row['Generators'].strip():
                generators = [g.strip() for g in row['Generators'].split(',') if g.strip()]
            
            retailers = []
            if row['Retailers'] and row['Retailers'].strip():
                retailers = [r.strip() for r in row['Retailers'].split(',') if r.strip()]
            
            # Update bus assignments
            st.session_state.network['buses'][bus_idx]['generators'] = generators
            st.session_state.network['buses'][bus_idx]['retailers'] = retailers
        
        # Regenerate generator and retailer lists based on new bus assignments
        _regenerate_generators_list()
        _regenerate_retailers_list()
        
        # Clear existing results to force re-analysis
        st.session_state.market_results = None
        st.session_state.powerflow_results = None
        
        st.success("✅ Bus configuration updated successfully!")
        st.info("🔄 Market and power flow results cleared - please re-run analysis")
        
    except Exception as e:
        st.error(f"Error updating bus configuration: {str(e)}")


def _regenerate_generators_list():
    """Regenerate generators list based on current bus assignments"""
    new_generators = []
    existing_gen_dict = {gen['name']: gen for gen in st.session_state.generators}
    
    # Collect all generator names from all buses
    all_generator_names = set()
    for bus_idx, bus in enumerate(st.session_state.network['buses']):
        for gen_name in bus.get('generators', []):
            all_generator_names.add((gen_name, bus_idx))
    
    # Create generators based on bus assignments
    for gen_name, bus_idx in all_generator_names:
        if gen_name in existing_gen_dict:
            # Update existing generator with new bus assignment
            existing_gen = existing_gen_dict[gen_name].copy()
            existing_gen['bus'] = bus_idx
            new_generators.append(existing_gen)
        else:
            # Create new generator with default parameters
            new_generators.append({
                'name': gen_name,
                'bus': bus_idx,
                'quantities': [100, 150],  # Default bid quantities
                'prices': [30, 45],        # Default bid prices
                'min_capacity': 50,
                'max_capacity': 250
            })
    
    st.session_state.generators = new_generators


def _regenerate_retailers_list():
    """Regenerate retailers list based on current bus assignments"""
    new_retailers = []
    existing_ret_dict = {ret['name']: ret for ret in st.session_state.retailers}
    
    # Collect all retailer names from all buses
    all_retailer_names = set()
    for bus_idx, bus in enumerate(st.session_state.network['buses']):
        for ret_name in bus.get('retailers', []):
            all_retailer_names.add((ret_name, bus_idx))
    
    # Create retailers based on bus assignments
    for ret_name, bus_idx in all_retailer_names:
        if ret_name in existing_ret_dict:
            # Update existing retailer with new bus assignment
            existing_ret = existing_ret_dict[ret_name].copy()
            existing_ret['bus'] = bus_idx
            new_retailers.append(existing_ret)
        else:
            # Create new retailer with default parameters
            new_retailers.append({
                'name': ret_name,
                'bus': bus_idx,
                'quantities': [120, 100],  # Default bid quantities
                'prices': [50, 35]         # Default bid prices
            })
    
    st.session_state.retailers = new_retailers


def render_network_topology():
    """Render network topology visualization"""
    st.markdown("## 🔌 Network Topology")
    
    # Create network graph
    G = nx.Graph()
    
    # Add nodes
    for i, bus in enumerate(st.session_state.network['buses']):
        G.add_node(i, name=bus['name'], type=bus['type'])
    
    # Add edges
    edge_labels = {}
    for line in st.session_state.network['lines']:
        G.add_edge(line['from_bus'], line['to_bus'])
        edge_labels[(line['from_bus'], line['to_bus'])] = f"R={line['resistance']:.3f}\nX={line['reactance']:.3f}"
    
    # Create layout
    pos = nx.spring_layout(G, seed=42, k=2, iterations=50)
    
    # Create plotly figure
    fig = go.Figure()
    
    # Add edges
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        
        fig.add_trace(go.Scatter(
            x=[x0, x1, None], 
            y=[y0, y1, None],
            mode='lines',
            line=dict(width=2, color='gray'),
            hoverinfo='none',
            showlegend=False
        ))
    
    # Add nodes
    node_colors = {'Slack': 'red', 'PV': 'blue', 'PQ': 'green'}
    
    for node in G.nodes():
        x, y = pos[node]
        bus = st.session_state.network['buses'][node]
        
        # Node info
        generators = bus.get('generators', [])
        retailers = bus.get('retailers', [])
        info_text = f"Bus {node + 1}: {bus['name']}<br>"
        info_text += f"Type: {bus['type']}<br>"
        if generators:
            info_text += f"Generators: {', '.join(generators)}<br>"
        if retailers:
            info_text += f"Retailers: {', '.join(retailers)}"
        
        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode='markers+text',
            marker=dict(
                size=30,
                color=node_colors.get(bus['type'], 'gray'),
                line=dict(width=2, color='white')
            ),
            text=[f"Bus {node + 1}"],
            textposition="middle center",
            textfont=dict(color="white", size=10),
            hovertext=info_text,
            hoverinfo='text',
            name=bus['type'],
            showlegend=False
        ))
    
    fig.update_layout(
        title="Power System Network Topology",
        showlegend=True,
        hovermode='closest',
        margin=dict(b=20,l=5,r=5,t=40),
        annotations=[
            dict(
                text="Red=Slack, Blue=PV, Green=PQ",
                showarrow=False,
                xref="paper", yref="paper",
                x=0.005, y=-0.002,
                xanchor='left', yanchor='bottom',
                font=dict(size=12)
            )
        ],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Network data table
    st.markdown("### 📊 Network Data")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Bus Data:**")
        bus_data = []
        for i, bus in enumerate(st.session_state.network['buses']):
            bus_data.append({
                'Bus': i + 1,
                'Name': bus['name'],
                'Type': bus['type'],
                'V_nom': bus['v_magnitude'],
                'Generators': ', '.join(bus.get('generators', [])) or '',
                'Retailers': ', '.join(bus.get('retailers', [])) or ''
            })
        
        df_buses = pd.DataFrame(bus_data)
        
        # Create editable bus dataframe
        edited_buses = st.data_editor(
            df_buses,
            column_config={
                'Bus': st.column_config.NumberColumn(
                    'Bus #',
                    disabled=True,
                    help='Bus number (cannot be edited)'
                ),
                'Name': st.column_config.TextColumn(
                    'Bus Name',
                    disabled=True,
                    help='Bus name (cannot be edited)'
                ),
                'Type': st.column_config.SelectboxColumn(
                    'Bus Type',
                    options=['Slack', 'PV', 'PQ'],
                    help='Bus type: Slack (reference), PV (generator), PQ (load)'
                ),
                'V_nom': st.column_config.NumberColumn(
                    'V_nom (pu)',
                    min_value=0.9,
                    max_value=1.1,
                    step=0.01,
                    format="%.3f",
                    help='Nominal voltage magnitude in per unit'
                ),
                'Generators': st.column_config.TextColumn(
                    'Generators',
                    help='Comma-separated list of generators (e.g., Gen1, Gen2)'
                ),
                'Retailers': st.column_config.TextColumn(
                    'Retailers',
                    help='Comma-separated list of retailers'
                )
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Check for changes and update bus data
        if not edited_buses.equals(df_buses):
            st.info("📝 Bus data has been modified")
            
            # Update button
            if st.button("🔄 Update Bus Configuration", type="primary"):
                _update_bus_configuration(edited_buses)
                st.rerun()
    
    with col2:
        st.markdown("**Line Data:**")
        line_data = []
        for i, line in enumerate(st.session_state.network['lines']):
            line_data.append({
                'Line_ID': i,
                'From': line['from_bus'] + 1,
                'To': line['to_bus'] + 1,
                'R (pu)': line['resistance'],
                'X (pu)': line['reactance'],
                'B (pu)': line['susceptance'],
                'Rating (MW)': line['rating']
            })
        
        df_lines = pd.DataFrame(line_data)
        
        # Create editable dataframe
        edited_lines = st.data_editor(
            df_lines,
            column_config={
                'Line_ID': st.column_config.NumberColumn(
                    'Line ID',
                    disabled=True,
                    help='Line identifier (cannot be edited)'
                ),
                'From': st.column_config.NumberColumn(
                    'From Bus',
                    disabled=True,
                    help='From bus number (cannot be edited)'
                ),
                'To': st.column_config.NumberColumn(
                    'To Bus',
                    disabled=True,
                    help='To bus number (cannot be edited)'
                ),
                'R (pu)': st.column_config.NumberColumn(
                    'R (pu)',
                    min_value=0.0,
                    max_value=1.0,
                    step=0.001,
                    format="%.4f",
                    help='Line resistance in per unit'
                ),
                'X (pu)': st.column_config.NumberColumn(
                    'X (pu)',
                    min_value=0.0,
                    max_value=1.0,
                    step=0.001,
                    format="%.4f",
                    help='Line reactance in per unit'
                ),
                'B (pu)': st.column_config.NumberColumn(
                    'B (pu)',
                    min_value=0.0,
                    max_value=1.0,
                    step=0.001,
                    format="%.4f",
                    help='Line susceptance in per unit'
                ),
                'Rating (MW)': st.column_config.NumberColumn(
                    'Rating (MW)',
                    min_value=0,
                    max_value=1000,
                    step=10,
                    help='Line rating in MW'
                )
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Update network data if changes are made
        if not edited_lines.equals(df_lines):
            st.info("📝 Line data has been modified")
            
            # Update button
            if st.button("💾 Update Line Data", type="primary"):
                # Update the network data with edited values
                for i, row in edited_lines.iterrows():
                    line_id = int(row['Line_ID'])
                    line = st.session_state.network['lines'][line_id]
                    line['resistance'] = float(row['R (pu)'])
                    line['reactance'] = float(row['X (pu)'])
                    line['susceptance'] = float(row['B (pu)'])
                    line['rating'] = int(row['Rating (MW)'])
                
                # Clear previous results since network changed
                st.session_state.powerflow_results = None
                st.session_state.optimal_dc_results = None
                st.session_state.dc_opf_powerflow_results = None
                
                st.success("✅ Line data updated successfully!")
                msg = ("ℹ️ Previous power flow results cleared. "
                       "Re-solve with new data.")
                st.info(msg)
                st.rerun()

def _tab_body() -> None:
    render_network_topology()


def render() -> None:
    dc_network.page(_tab_body)
