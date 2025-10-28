#!/usr/bin/env python3
"""Streamlit web UI for the Flood Ingress Simulation.

This app is a thin presentation layer that imports parsing and model
classes from `main.py` and plotting helpers from `viz.py`.

Usage:
    pip install -r requirements.txt
    streamlit run streamlit_app.py

Notes:
 - Uploaded ingress text is written to a temporary file and parsed using
   the authoritative `parse_ingress_file` from `main.py` to avoid duplicate
   parsing logic and to reuse the validated path-based parser.
 - The app uses `viz.py` to generate PNG previews and animations. The
   animation generation may require `ffmpeg` on the system if PillowWriter
   cannot write GIFs.
"""
import io
import os
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image

# Import authoritative logic from main.py
from main import Building, Simulation, parse_external_text, parse_ingress_file, parse_external_file, parse_ingress_text

import viz


st.set_page_config(page_title='Water Ingress Simulator', layout='wide')


def read_uploaded_text(uploaded) -> str:
    if uploaded is None:
        return ''
    return uploaded.getvalue().decode('utf-8')


def save_temp_file_from_bytes(data_bytes, suffix=''):
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tf.write(data_bytes)
    tf.flush()
    tf.close()
    return tf.name


st.title('Water Ingress Simulator (Web UI)')

with st.sidebar:
    st.header('Inputs')
    uploaded_external = st.file_uploader('Upload external levels CSV (time,level)', type=['csv', 'txt'])
    uploaded_ingress = st.file_uploader('Upload ingress file (height,area,coeff[,name])', type=['txt', 'csv'])
    floor_area = st.number_input('Floor area (m^2)', value=50.0, min_value=0.1)
    time_unit = st.selectbox('Time units for hydrograph and timestep', options=['seconds', 'minutes', 'hours'], index=1)
    timestep = st.number_input('Simulation timestep (in selected time units)', value=1.0 if time_unit != 'seconds' else 60.0, min_value=0.0, step=1.0)
    make_anim = st.checkbox('Generate animation (may be slow)', value=False)
    st.markdown('---')
    st.subheader('Manual input (optional)')
    manual_external = st.checkbox('Provide external levels manually (table)')
    manual_ingress = st.checkbox('Provide ingress entries manually (table)')
    run_button = st.button('Run simulation')

col1, col2 = st.columns(2)

with col1:
    st.subheader('External levels (preview)')
    external_text = None
    ingress_text = None
    # prefer manual table if provided
    external_table = None
    if manual_external:
        # provide a small example table for the user to edit
        example_ext = [{'time': 0.0, 'level': 0.0}, {'time': 1.0, 'level': 0.2}]
        if hasattr(st, 'experimental_data_editor'):
            external_table = st.experimental_data_editor(example_ext, num_rows='dynamic')
        elif hasattr(st, 'data_editor'):
            external_table = st.data_editor(example_ext, num_rows='dynamic')
        else:
            external_text_area = st.text_area('Paste CSV (time,level) lines here', value='0,0.0\n1,0.2')
            external_table = None
            external_text = external_text_area

    if not manual_external and uploaded_external is not None:
        try:
            external_text = read_uploaded_text(uploaded_external)
            # attempt to parse and show preview
            times, levels = parse_external_text(external_text)
            # write to temp preview
            preview_path = os.path.join(tempfile.gettempdir(), 'streamlit_external_preview.png')
            viz.save_external_preview(times, levels, preview_path, time_unit=time_unit)
            st.image(preview_path, width='stretch')
        except Exception as e:
            st.error(f'Failed to parse external data: {e}')
    else:
        st.info('Upload a CSV or paste data into the sidebar to preview external levels.')

with col2:
    st.subheader('Ingress definitions (preview)')
    ingress_table = None
    if manual_ingress:
        example_ing = [{'height': 0.0, 'area': 0.01, 'coeff': 0.6, 'name': 'wall_crack'}]
        if hasattr(st, 'experimental_data_editor'):
            ingress_table = st.experimental_data_editor(example_ing, num_rows='dynamic')
        elif hasattr(st, 'data_editor'):
            ingress_table = st.data_editor(example_ing, num_rows='dynamic')
        else:
            ingress_text_area = st.text_area('Paste ingress lines (height,area,coeff[,name])', value='0.0,0.01,0.6,wall_crack')
            ingress_table = None
            ingress_text = ingress_text_area

    if not manual_ingress and uploaded_ingress is not None:
        # save to temp file and call authoritative parser
        try:
            tmp_ing_path = save_temp_file_from_bytes(uploaded_ingress.getvalue(), suffix='.txt')
            ingress_list = parse_ingress_file(tmp_ing_path)
            preview_path = os.path.join(tempfile.gettempdir(), 'streamlit_ingress_preview.png')
            # prefer the ingress locations plot for the web UI; fall back to a simple preview
            try:
                viz.save_ingress_locations(ingress_list, preview_path)
            except Exception:
                viz.save_ingress_preview(ingress_list, preview_path)
            st.image(preview_path, width='stretch')
        except Exception as e:
            st.error(f'Failed to parse ingress data: {e}')
    else:
        st.info('Upload an ingress file to preview areas and locations.')


if run_button:
    # Sanity checks
    # Accept either uploaded files or manual table input
    if not (uploaded_external or manual_external) or not (uploaded_ingress or manual_ingress):
        st.error('Please provide both external levels and ingress definitions (either upload files or use the manual tables).')
    else:
        try:
            st.sidebar.info('Preparing inputs...')
            # Determine external source (manual table takes precedence)
            if manual_external and external_table is not None:
                # convert table to CSV-like text
                def table_to_text(table, cols):
                    lines = []
                    # pandas DataFrame
                    if hasattr(table, 'to_dict'):
                        records = table.to_dict(orient='records')
                    else:
                        records = list(table)
                    for r in records:
                        try:
                            t = r.get('time') if 'time' in r else r.get('Time') if 'Time' in r else list(r.values())[0]
                            h = r.get('level') if 'level' in r else r.get('Level') if 'Level' in r else list(r.values())[1]
                            lines.append(f"{t},{h}")
                        except Exception:
                            continue
                    return '\n'.join(lines)

                ext_text = table_to_text(external_table, ['time', 'level'])
                times, levels = parse_external_text(ext_text)
            elif not manual_external and uploaded_external is not None:
                ext_text = read_uploaded_text(uploaded_external)
                times, levels = parse_external_text(ext_text)
            else:
                # manual_external checked but text-area fallback
                times, levels = parse_external_text(external_text)
            # keep original units for preview
            orig_times = list(times)

            # Determine ingress source (manual table takes precedence)
            if manual_ingress and ingress_table is not None:
                # convert ingress table to text lines
                def ingress_table_to_text(table):
                    lines = []
                    if hasattr(table, 'to_dict'):
                        records = table.to_dict(orient='records')
                    else:
                        records = list(table)
                    for r in records:
                        try:
                            h = r.get('height') if 'height' in r else list(r.values())[0]
                            area = r.get('area') if 'area' in r else list(r.values())[1]
                            coeff = r.get('coeff') if 'coeff' in r else list(r.values())[2]
                            name = r.get('name') if 'name' in r else (list(r.values())[3] if len(list(r.values())) > 3 else '')
                            if name:
                                lines.append(f"{h},{area},{coeff},{name}")
                            else:
                                lines.append(f"{h},{area},{coeff}")
                        except Exception:
                            continue
                    return '\n'.join(lines)

                ingress_text = ingress_table_to_text(ingress_table)
                ingress_list = parse_ingress_text(ingress_text)
            elif not manual_ingress and uploaded_ingress is not None:
                tmp_ing_path = save_temp_file_from_bytes(uploaded_ingress.getvalue(), suffix='.txt')
                ingress_list = parse_ingress_file(tmp_ing_path)
            else:
                # manual_ingress with text-area fallback
                ingress_list = parse_ingress_text(ingress_text)

            building = Building(floor_area)
            # compute unit multiplier and convert times/dt to seconds for simulation
            mul = 1.0
            if time_unit.startswith('min'):
                mul = 60.0
            elif time_unit.startswith('hour'):
                mul = 3600.0
            times_seconds = [t * mul for t in times]
            dt_seconds = float(timestep) * mul
            # pass user-controlled timestep (converted to seconds) into the Simulation
            sim = Simulation(building, ingress_list, times_seconds, levels, dt=dt_seconds)

            progress_bar = st.progress(0)
            status_text = st.empty()

            def progress_cb(p):
                try:
                    progress_bar.progress(min(100, int(p * 100)))
                except Exception:
                    pass

            status_text.text('Running simulation...')
            sim_times, sim_levels = sim.run(progress_callback=progress_cb, verbose=False)
            status_text.text('Simulation complete')

            # helper: sample external hydrograph (times_seconds/h_levels) to sim_times
            def sample_external(sim_times_local, t_ext_local, h_ext_local):
                sampled = []
                j = 0
                for t in sim_times_local:
                    while j < len(t_ext_local) - 1 and t >= t_ext_local[j+1]:
                        j += 1
                    if j < len(t_ext_local) - 1:
                        t1, h1 = t_ext_local[j], h_ext_local[j]
                        t2, h2 = t_ext_local[j+1], h_ext_local[j+1]
                        if t2 != t1:
                            frac = (t - t1) / (t2 - t1)
                            sampled.append(h1 + frac * (h2 - h1))
                        else:
                            sampled.append(h1)
                    else:
                        sampled.append(h_ext_local[-1] if h_ext_local else 0.0)
                return sampled

            # Only produce the simulation result (and optionally the animation).
            outdir = tempfile.mkdtemp(prefix='streamlit_sim_')
            sim_out = os.path.join(outdir, 'simulation_result.png')
            # prepare display times (convert seconds back to selected units) and sampled external
            sim_times_display = [t / mul for t in sim_times]
            sampled_external = sample_external(sim_times, times_seconds, levels)
            viz.save_simulation_result(sim_times_display, sim_levels, sampled_external, sim_out, time_unit=time_unit)
            st.image(sim_out, caption='Simulation result', width='stretch')

            # Download button for the simulation PNG
            with open(sim_out, 'rb') as f:
                sim_bytes = f.read()
            st.download_button('Download simulation PNG', data=sim_bytes, file_name='simulation_result.png')

            if make_anim:
                anim_path = os.path.join(outdir, 'simulation_animation.gif')
                status_text.text('Generating animation (this can take a while)...')
                try:
                    sampled_external = sample_external(sim_times, times_seconds, levels)
                    sim_times_display = [t / mul for t in sim_times]
                    viz.generate_animation(sim_times_display, sim_levels, sampled_external, ingress_list, anim_path, time_unit=time_unit)
                    with open(anim_path, 'rb') as f:
                        anim_bytes = f.read()
                    # Display animated GIF inline (more reliable across browsers)
                    try:
                        st.image(anim_bytes, caption='Simulation animation', width='stretch', output_format='GIF')
                    except TypeError:
                        # older Streamlit versions may not support output_format; fall back to video
                        st.video(anim_path)
                    st.download_button('Download animation', data=anim_bytes, file_name='simulation_animation.gif')
                except Exception as e:
                    st.error(f'Failed to generate animation: {e}')

        except Exception as exc:
            st.exception(exc)
