#      doesn't have something to check, instead of inventing an answer.
# =====================================================================
def get_copilot_response(prompt, history):
    try:
        api_key = st.secrets["anthropic"]["api_key"]
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = (
            "You are the Shoir-IE Copilot, embedded in an industrial engineering and "
            "operations research platform covering MILP/optimization, inventory, supply chain, APS/MES, "
            "facility layout, quality/reliability, simulation, digital twins, sustainability, economics, "
            "workforce, KPI Studio, engineering methods/equations, scenario versioning, process mining, "
            "drift monitoring, decision verification, DMAIC/A3, templates and platform diagnostics. "
            "Use the shared Platform Excellence layer as part of your operating context. " + copilot_context() + " Available governed Copilot tools are: " + ", ".join(t[0] for t in COPILOT_TOOLS) + ". " 
            "Recommend the most relevant existing module or workflow from the live platform catalog. "
            "Prefer validation, explainability, scenario analysis and auditable exports before action. "
            "Be concise and concrete. If asked to run something you can't execute directly, name the exact "
            "module to use. Never invent numbers, connectivity, model results or data you don't have."
        )
        msgs = [{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ("user", "assistant")]
        msgs.append({"role": "user", "content": prompt})
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=600,
            system=system_prompt,
            messages=msgs
        )
        return response.content[0].text
    except Exception:
        pass  # no key configured, package missing, or the call failed - fall through

    p = prompt.lower().strip()

    if any(w in p for w in ["hello", "hi", "hey", "what's up", "whats up"]):
        return (f"Hello {st.session_state.get('current_user', 'there')}! I can run the MILP optimizer, "
                f"report your real warehouse/customer/fleet/inventory data, or point you to the right "