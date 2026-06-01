def _bloco_protocolos_redesim_dashboard():
    """Pipeline Viabilidade → Licenciamento com botões de ação direta."""
    from datetime import datetime as _dt
    todos = listar_todos_protocolos()

    via_andamento = [p for p in todos
                     if p["tipo"] == TIPO_PROTOCOLO_VIABILIDADE
                     and p["status"] not in (STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA)
                     and not p.get("substituido_por_id")]
    via_aprovadas = [p for p in todos
                     if p["tipo"] == TIPO_PROTOCOLO_VIABILIDADE
                     and p["status"] == "Aprovada"
                     and not p.get("substituido_por_id")]
    lic_andamento = [p for p in todos
                     if p["tipo"] == TIPO_PROTOCOLO_LICENCIAMENTO
                     and p["status"] not in (STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA)
                     and not p.get("substituido_por_id")]

    todos_ativos = via_andamento + via_aprovadas + lic_andamento
    if not todos_ativos:
        return

    hoje = _dt.now()

    def _dias(p):
        ds = p.get("data_solicitacao")
        if not ds:
            return 0
        try:
            return (hoje - _dt.strptime(ds, "%Y-%m-%d")).days
        except Exception:
            return 0

    def _cor(dias):
        if dias >= DIAS_VERMELHO:
            return "🔴"
        if dias >= DIAS_AMARELO:
            return "🟡"
        return "🟢"

    with st.container(border=True):
        st.markdown(
            "<div class='bloco-header'>📜 Protocolos REDESIM em andamento</div>",
            unsafe_allow_html=True,
        )
        all_dias = [_dias(p) for p in todos_ativos]
        _r = sum(1 for d in all_dias if d >= DIAS_VERMELHO)
        _y = sum(1 for d in all_dias if DIAS_AMARELO <= d < DIAS_VERMELHO)
        _g = sum(1 for d in all_dias if d < DIAS_AMARELO)
        st.markdown(_health_bar_html(_r, _y, _g), unsafe_allow_html=True)

        col_via, col_arrow, col_lic = st.columns([5, 1, 5])

        with col_via:
            st.markdown("#### 📋 Etapa 1 — Viabilidade")
            st.caption(
                f"{len(via_andamento)} em análise · "
                f"{len(via_aprovadas)} aprovada(s) aguardando"
            )
            for p in via_andamento + via_aprovadas:
                dias = _dias(p)
                cor = _cor(dias)
                razao = p.get("razao_social", "?")
                with st.container(border=True):
                    ca, cb = st.columns([3, 1])
                    with ca:
                        st.markdown(f"{cor} **{razao}**")
                        st.caption(
                            f"`{p['numero_protocolo']}` · {p['status']} · {dias}d"
                        )
                    with cb:
                        st.caption(p.get("data_solicitacao") or "—")

                    if p["status"] == "Aprovada":
                        st.success("✅ Viabilidade deferida — pronto para Licenciamento")
                        if st.button(
                            "▶️ Iniciar Licenciamento",
                            key=f"ini_lic_{p['id']}",
                            use_container_width=True,
                            type="primary",
                        ):
                            novo_id = criar_protocolo_redesim(
                                empresa_id=p["empresa_id"],
                                tipo=TIPO_PROTOCOLO_LICENCIAMENTO,
                                numero_protocolo=p["numero_protocolo"],
                                data_solicitacao=p.get("data_solicitacao"),
                                status="Em análise",
                                observacoes=(
                                    "Licenciamento iniciado após viabilidade aprovada.\n"
                                    "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                ),
                            )
                            st.toast(f"Licenciamento registrado (ID {novo_id}).")
                            _invalidar_cache_db()
                            import time as _t
                            _t.sleep(0.8)
                            st.rerun()
                    else:
                        b1, b2, b3 = st.columns(3)
                        with b1:
                            if st.button(
                                "✅ Deferida",
                                key=f"def_{p['id']}",
                                use_container_width=True,
                                type="primary",
                            ):
                                _, info_g = atualizar_status_protocolo_com_gestta(
                                    p["id"], "Aprovada",
                                    observacoes=(
                                        "Viabilidade deferida pela Prefeitura.\n"
                                        "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                    ),
                                )
                                st.toast("Viabilidade aprovada!")
                                _mostrar_feedback_gestta(info_g, "Aprovada")
                                _invalidar_cache_db()
                                import time as _t
                                _t.sleep(0.8)
                                st.rerun()
                        with b2:
                            if st.button(
                                "❌ Indeferida",
                                key=f"ind_{p['id']}",
                                use_container_width=True,
                            ):
                                _, info_g = atualizar_status_protocolo_com_gestta(
                                    p["id"], "Indeferida",
                                    observacoes=(
                                        "Viabilidade indeferida.\n"
                                        "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                    ),
                                )
                                st.toast("Indeferida.")
                                _mostrar_feedback_gestta(info_g, "Indeferida")
                                _invalidar_cache_db()
                                import time as _t
                                _t.sleep(0.8)
                                st.rerun()
                        with b3:
                            if st.button(
                                "🚫 Cancelar",
                                key=f"can_{p['id']}",
                                use_container_width=True,
                            ):
                                _, info_g = atualizar_status_protocolo_com_gestta(
                                    p["id"], "Cancelada",
                                    observacoes=(
                                        "Protocolo cancelado.\n"
                                        "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                    ),
                                )
                                st.toast("Cancelado.")
                                _mostrar_feedback_gestta(info_g, "Cancelada")
                                _invalidar_cache_db()
                                import time as _t
                                _t.sleep(0.8)
                                st.rerun()

        with col_arrow:
            st.markdown(
                "<div style='text-align:center;font-size:2rem;padding-top:3rem;'>→</div>",
                unsafe_allow_html=True,
            )

        with col_lic:
            st.markdown("#### 📄 Etapa 2 — Licenciamento (CLI)")
            st.caption(f"{len(lic_andamento)} em andamento")
            if not lic_andamento:
                st.info("Nenhum licenciamento em andamento ainda.")
            for p in lic_andamento:
                dias = _dias(p)
                cor = _cor(dias)
                razao = p.get("razao_social", "?")
                with st.container(border=True):
                    ca, cb = st.columns([3, 1])
                    with ca:
                        st.markdown(f"{cor} **{razao}**")
                        st.caption(
                            f"`{p['numero_protocolo']}` · {p['status']} · {dias}d"
                        )
                    with cb:
                        st.caption(p.get("data_solicitacao") or "—")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button(
                            "✅ CLI Emitido",
                            key=f"cli_{p['id']}",
                            use_container_width=True,
                            type="primary",
                        ):
                            _, info_g = atualizar_status_protocolo_com_gestta(
                                p["id"], "Concluída",
                                observacoes=(
                                    "CLI emitido. Licença de Funcionamento concluída.\n"
                                    "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                ),
                            )
                            st.toast("CLI emitido! Cobrança DOMÍNIO gerada automaticamente.")
                            _mostrar_feedback_gestta(info_g, "Concluída")
                            _invalidar_cache_db()
                            import time as _t
                            _t.sleep(0.8)
                            st.rerun()
                    with b2:
                        if st.button(
                            "❌ Indeferida",
                            key=f"lic_ind_{p['id']}",
                            use_container_width=True,
                        ):
                            _, info_g = atualizar_status_protocolo_com_gestta(
                                p["id"], "Indeferida",
                                observacoes=(
                                    "Licenciamento indeferido.\n"
                                    "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                ),
                            )
                            st.toast("Indeferido.")
                            _mostrar_feedback_gestta(info_g, "Indeferida")
                            _invalidar_cache_db()
                            import time as _t
                            _t.sleep(0.8)
                            st.rerun()

        st.caption(
            f"🔴 ≥ {DIAS_VERMELHO}d · 🟡 ≥ {DIAS_AMARELO}d · 🟢 ok. "
            "Histórico completo em **🏢 Empresas / REDESIM**."
        )

