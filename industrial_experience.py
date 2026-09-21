    c1.metric("Core capabilities", "{}/60".format(stats["implemented"]), "active")
    c2.metric("Research studies" if is_research_lab else "Saved studies", "{:,}".format(research_studies if is_research_lab else projects), "protocols" if is_research_lab else "persistent")
    c3.metric("Decision records", "{:,}".format(decisions), "governed")
    c4.metric("Active jobs", "{:,}".format(jobs), "live")

    if is_research_lab:
        st.markdown("### 🔬 Research Study Protocol")
        st.caption("Define the research question, hypotheses, variables, controls, sampling plan and reproducibility settings before the main experiment. This is a local protocol record and integrity control; it is not external preregistration.")
        active_protocol_id = st.session_state.get("sx_research_study_id")
        active_protocol = load_research_protocol(active_protocol_id) if active_protocol_id else None
        locked = bool(active_protocol and active_protocol.get("protocol_locked"))
        methods = ["Controlled simulation benchmark", "Design of experiments (DOE)", "Cross-domain transfer benchmark", "Monte Carlo study", "Hybrid simulation + optimization"]
        domains = ["Manufacturing", "Warehouse / inventory", "Supply chain", "Maintenance", "Quality", "Energy"]
        method_index = methods.index(active_protocol["methodology"]) if active_protocol and active_protocol.get("methodology") in methods else 2
        primary_index = domains.index(active_protocol["primary_domain"]) if active_protocol and active_protocol.get("primary_domain") in domains else 0
        transfer_index = domains.index(active_protocol["transfer_domain"]) if active_protocol and active_protocol.get("transfer_domain") in domains else 2

            r1, r2 = st.columns([1.7, 1])
        with r1:
            research_title = st.text_input("Study title", value=(active_protocol or {}).get("title", "Industrial Decision Genome — Experiment 001"), disabled=locked, key="sx_research_title_" + key)
            research_question = st.text_area("Research question", value=(active_protocol or {}).get("research_question", "Can transferable industrial decision structures improve AI decision-making on previously unseen industrial environments and compound disruptions?"), height=90, disabled=locked, key="sx_research_question_" + key)
            objective = st.text_area("Study objective", value=(active_protocol or {}).get("objective", "Determine whether industrial decision knowledge transfers across domains without retraining on the target domain."), height=70, disabled=locked, key="sx_research_objective_" + key)
        with r2:
            methodology = st.selectbox("Methodology", methods, index=method_index, disabled=locked, key="sx_research_methodology_" + key)
            primary_endpoint = st.text_input("Primary endpoint", value=(active_protocol or {}).get("primary_endpoint", "Normalized decision regret"), disabled=locked, key="sx_research_endpoint_" + key)
            primary_domain = st.selectbox("Primary domain", domains, index=primary_index, disabled=locked, key="sx_research_primary_domain_" + key)
            transfer_domain = st.selectbox("Unseen / transfer domain", domains, index=transfer_index, disabled=locked, key="sx_research_transfer_domain_" + key)

        h1, h2 = st.columns(2)
        with h1:
            hypothesis = st.text_area("Primary hypothesis (H1)", value=(active_protocol or {}).get("hypothesis", "A transferable decision representation will retain measurable performance on an unseen industrial environment compared with documented baselines."), height=80, disabled=locked, key="sx_research_h1_" + key)
        with h2:
            null_hypothesis = st.text_area("Null hypothesis (H0)", value=(active_protocol or {}).get("null_hypothesis", "Transferable decision representations will not produce a reliable improvement on unseen industrial environments after controlling for baseline performance and variance."), height=80, disabled=locked, key="sx_research_h0_" + key)

        v1, v2, v3 = st.columns(3)
        with v1:
            secondary_metrics = st.text_input("Secondary metrics", value=", ".join((active_protocol or {}).get("secondary_metrics", ["cost", "throughput", "service", "risk", "inventory", "carbon"])), disabled=locked, key="sx_research_secondary_" + key)
            independent_variables = st.text_input("Independent variables", value=", ".join((active_protocol or {}).get("independent_variables", ["decision method", "domain", "disruption type"])), disabled=locked, key="sx_research_independent_" + key)
            controls = st.text_input("Controls / covariates", value=", ".join((active_protocol or {}).get("controls", ["scenario seed", "objective weights", "constraint set"])), disabled=locked, key="sx_research_controls_" + key)
        with v2:
            sample_size = st.number_input("Scenario count", min_value=10, max_value=100000, value=int((active_protocol or {}).get("sample_size", 100)), step=10, disabled=locked, key="sx_research_sample_size_" + key)
            replications = st.number_input("Replications / scenario", min_value=1, max_value=10000, value=int((active_protocol or {}).get("replications", 30)), step=1, disabled=locked, key="sx_research_replications_" + key)
            random_seed = st.number_input("Random seed", min_value=0, max_value=2147483647, value=int((active_protocol or {}).get("random_seed", 2026)), step=1, disabled=locked, key="sx_research_seed_" + key)
        with v3:
            alpha = st.number_input("Significance level (α)", min_value=0.001, max_value=0.20, value=float((active_protocol or {}).get("alpha", 0.05)), step=0.01, format="%.3f", disabled=locked, key="sx_research_alpha_" + key)
            confidence_level = st.number_input("Confidence level", min_value=0.80, max_value=0.999, value=float((active_protocol or {}).get("confidence_level", 0.95)), step=0.01, format="%.3f", disabled=locked, key="sx_research_confidence_" + key)
            data_source = st.text_input("Data source", value=(active_protocol or {}).get("data_source", "Shoir-IE controlled synthetic scenarios; later external validation dataset"), disabled=locked, key="sx_research_data_source_" + key)

        baseline_definition = st.text_area("Baseline definition", value=(active_protocol or {}).get("baseline_definition", "A fixed documented baseline policy plus a classical optimization baseline where applicable."), height=60, disabled=locked, key="sx_research_baseline_" + key)
        treatment_definition = st.text_area("Treatment / experimental condition", value=(active_protocol or {}).get("treatment_definition", "Shoir-IE decision representation evaluated on held-out combinations and an unseen transfer domain."), height=60, disabled=locked, key="sx_research_treatment_" + key)
        planned_tests = st.text_input("Planned statistical tests", value=", ".join((active_protocol or {}).get("planned_tests", ["confidence intervals", "paired comparison", "effect size", "bootstrap sensitivity"])), disabled=locked, key="sx_research_tests_" + key)

        ic1, ic2 = st.columns(2)
        with ic1:
            inclusion_criteria = st.text_area("Inclusion criteria", value=(active_protocol or {}).get("inclusion_criteria", "Valid scenario definitions; finite numeric inputs; all required constraints specified."), height=60, disabled=locked, key="sx_research_inclusion_" + key)
        with ic2:
            exclusion_criteria = st.text_area("Exclusion criteria", value=(active_protocol or {}).get("exclusion_criteria", "Failed validation; malformed scenarios; missing primary outcome; solver/runtime failure not attributable to decision method."), height=60, disabled=locked, key="sx_research_exclusion_" + key)

        protocol_notes = st.text_area("Protocol notes / limitations", value=(active_protocol or {}).get("protocol_notes", "Record protocol amendments explicitly instead of silently changing the main test specification."), height=70, disabled=locked, key="sx_research_notes_" + key)
        lock_protocol = st.checkbox("Lock protocol after saving (local integrity lock)", value=locked, disabled=locked, key="sx_research_lock_" + key, help="Locks this local record. It is not external preregistration.")
        save_protocol = st.button("💾 Save Research Study & Protocol" if not locked else "🔒 Protocol Locked", type="primary", use_container_width=True, disabled=locked, key="sx_save_research_protocol_" + key)

        if save_protocol:
            validation_errors = []
            if not research_title.strip(): validation_errors.append("Study title is required.")
            if len(research_question.strip()) < 20: validation_errors.append("Research question should be at least 20 characters.")
            if len(hypothesis.strip()) < 20: validation_errors.append("H1 should be at least 20 characters.")
            if len(null_hypothesis.strip()) < 20: validation_errors.append("H0 should be at least 20 characters.")
            if not primary_endpoint.strip(): validation_errors.append("Primary endpoint is required.")
            if primary_domain == transfer_domain: validation_errors.append("Primary and transfer domains must differ for this cross-domain study.")
            if not (0.0 < alpha < 1.0): validation_errors.append("Significance level must be between 0 and 1.")
            if not (0.0 < confidence_level < 1.0): validation_errors.append("Confidence level must be between 0 and 1.")
            if validation_errors:
                for error in validation_errors: st.error(error)
            else:
                payload = {
                    "title": research_title,
                    "objective": objective,
                    "research_question": research_question,
                    "hypothesis": hypothesis,
                    "null_hypothesis": null_hypothesis,
                    "methodology": methodology,
                    "primary_domain": primary_domain,
                    "transfer_domain": transfer_domain,
                    "primary_endpoint": primary_endpoint,
                    "secondary_metrics": _research_list(secondary_metrics),
                    "independent_variables": _research_list(independent_variables),
                    "controls": _research_list(controls),
                    "baseline_definition": baseline_definition,
                    "treatment_definition": treatment_definition,
                    "sample_size": int(sample_size),
                    "replications": int(replications),
                    "random_seed": int(random_seed),
                    "alpha": float(alpha),
                    "confidence_level": float(confidence_level),
                    "planned_tests": _research_list(planned_tests),
                    "inclusion_criteria": inclusion_criteria,
                    "exclusion_criteria": exclusion_criteria,
                    "data_source": data_source,
                    "protocol_notes": protocol_notes,
                    "protocol_locked": bool(lock_protocol),
                    "module": module,
                    "tier": tier,
                }
                pid = save_project(research_title, module, username, {"research_protocol": payload, "protocol_type": "local_research_protocol"})
                rid, phash = create_research_protocol(pid, payload, username)
                st.session_state["sx_research_study_id"] = pid
                st.session_state["sx_research_id"] = rid
                st.session_state["sx_research_protocol_hash"] = phash
                st.success("Research study saved: {} · Protocol {} · SHA-256 {}…".format(pid, rid, phash[:20]))
                if lock_protocol:
                    st.info("Protocol integrity lock is ON. This is an internal reproducibility control, not external preregistration.")

        active_id = st.session_state.get("sx_research_study_id")
        if active_id:
            frame = research_protocol_frame(active_id)
            if not frame.empty:
                st.dataframe(frame, use_container_width=True, hide_index=True)

    # A compact visual pulse keeps the workspace informative without making
    # every module feel like a dashboard overload.
    pulse = pd.DataFrame({
        "State": ["Implemented", "Integration-ready"],
        "Capabilities": [stats["implemented"], stats["integration_ready"]],
    })
    pc1, pc2 = st.columns([1.35, 2.65])
    with pc1:
        st.markdown("**Platform pulse**")
        st.progress(stats["implemented"] / max(1, stats["total"]), text="{}/60 capabilities active".format(stats["implemented"]))
    with pc2:
        fig = px.bar(
            pulse,
            x="Capabilities",
            y="State",
            orientation="h",
            text="Capabilities",
            title="Experience readiness",
        )
        fig.update_layout(height=155, margin=dict(l=10, r=10, t=38, b=8), showlegend=False)
        fig.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    steps = st.columns(6)
    for col, label in zip(steps, ["01 Prepare", "02 Validate", "03 Run", "04 Inspect", "05 Decide", "06 Export"]):
        col.markdown("<div class='sx-step'>✓ {}</div>".format(label), unsafe_allow_html=True)

    a, b, c, d, e = st.columns(5)
    if is_research_lab:
        a.info("Research protocol above")
    elif module == "Engineering Decision Center":
        if a.button("🔬 Open Research Lab", use_container_width=True, key="sx_open_research_" + key):
            # The sidebar selectbox is already instantiated on this run, so
            # mutating its widget-owned session key here raises
            # StreamlitWidgetAlreadyInstantiatedError. Set a one-run request
            # flag instead; app.py consumes it before creating the selectbox.
            st.session_state["open_research_lab_requested"] = True
            st.rerun()
        a.caption("Research studies start in Experiment Lab; return here later for governed decision cards.")
    else:
        if a.button("💾 Save Study", use_container_width=True, key="sx_save_" + key):