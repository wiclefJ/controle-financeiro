import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import base64

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CONEXÃO
# ==========================================
st.set_page_config(page_title="Controle Financeiro", layout="wide")
st.markdown("""<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">""", unsafe_allow_html=True)

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# ==========================================
# 2. SISTEMA DE LOGIN (AUTENTICAÇÃO)
# ==========================================
lista_dependentes = supabase.table("dependentes").select("*").execute().data
if 'usuario_logado' not in st.session_state:
    st.session_state.usuario_logado = None

if st.session_state.usuario_logado is None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'><i class='fa-solid fa-lock'></i> Acesso ao Sistema</h2>", unsafe_allow_html=True)
        with st.form("form_login"):
            usuario_selecionado = st.selectbox("Quem é você?", lista_dependentes, format_func=lambda x: x['nome'])
            senha_digitada = st.text_input("Senha:", type="password")
            
            if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                senha_banco = usuario_selecionado.get('senha')
                senha_mestre = st.secrets.get("SENHA_UNIVERSAL", "wiclef2026") # Plano B seguro
                
                if (senha_banco and senha_digitada == senha_banco) or senha_digitada == senha_mestre:
                    st.session_state.usuario_logado = usuario_selecionado
                    st.rerun()
                else:
                    st.error("Senha incorreta ou não cadastrada!")
    st.stop()

usuario = st.session_state.usuario_logado

# ==========================================
# 3. MENU LATERAL E FILTROS
# ==========================================
st.sidebar.title("Bem-vindo(a)!")
st.sidebar.write(f"👤 **{usuario['nome']}** ({usuario.get('perfil', 'usuario').upper()})")
if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
    st.session_state.usuario_logado = None
    st.rerun()

st.sidebar.divider()
st.sidebar.write("🔎 **Filtros de Período**")
hoje = date.today()
primeiro_dia = hoje.replace(day=1)
filtro_datas = st.sidebar.date_input("Intervalo:", value=(primeiro_dia, hoje), format="DD/MM/YYYY")

if len(filtro_datas) == 2: data_inicio, data_fim = filtro_datas
else: data_inicio, data_fim = filtro_datas[0], filtro_datas[0]

# ==========================================
# 4. BUSCA DE DADOS COM PERMISSÕES (RBAC)
# ==========================================
if usuario.get('perfil') == 'admin':
    dependentes_ativos = lista_dependentes
    todas_contas = supabase.table("acertos_cartao").select("*").execute().data
    lista_ganhos = supabase.table("ganhos").select("*").execute().data
else:
    dependentes_ativos = [usuario]
    todas_contas = supabase.table("acertos_cartao").select("*").eq("dependente_id", usuario['id']).execute().data
    lista_ganhos = supabase.table("ganhos").select("*").eq("dependente_id", usuario['id']).execute().data

contas_pendentes = [c for c in todas_contas if c['status'] == 'Pendente']
id_para_nome = {p['id']: p['nome'] for p in lista_dependentes}

contas_filtradas = []
for c in contas_pendentes:
    venc_str = c.get('data_vencimento')
    if venc_str and (data_inicio <= datetime.strptime(venc_str[:10], '%Y-%m-%d').date() <= data_fim):
        contas_filtradas.append(c)

saldos_devedores = {p['id']: 0.0 for p in dependentes_ativos}
for c in contas_filtradas: saldos_devedores[c['dependente_id']] += c['valor']

ganhos_filtrados = []
for g in lista_ganhos:
    reg_str = g.get('data_recebimento') or g.get('data_registro')
    if reg_str and (data_inicio <= datetime.strptime(reg_str[:10], '%Y-%m-%d').date() <= data_fim):
        ganhos_filtrados.append(g)
            
recebimentos = {p['nome']: 0.0 for p in dependentes_ativos}
for g in ganhos_filtrados: recebimentos[id_para_nome.get(g['dependente_id'])] += g['valor']

contas_atrasadas = [c for c in contas_pendentes if c.get('data_vencimento') and datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').date() < hoje]

# ==========================================
# 5. JANELA DE DETALHES (MODAL)
# ==========================================
@st.dialog("🔍 Detalhes do Membro", width="large")
def mostrar_detalhes(pessoa_id, nome_pessoa, d_inicio, d_fim):
    st.markdown(f"### Histórico de {nome_pessoa}")
    st.write(f"**Período:** {d_inicio.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}")
    
    resp_contas_membro = supabase.table("acertos_cartao").select("*").eq("dependente_id", pessoa_id).execute().data
    resp_ganhos_membro = supabase.table("ganhos").select("*").eq("dependente_id", pessoa_id).execute().data
    
    c_filtradas = [c for c in resp_contas_membro if c.get('data_vencimento') and (d_inicio <= datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').date() <= d_fim)]
    g_filtrados = [g for g in resp_ganhos_membro if (g.get('data_recebimento') or g.get('data_registro')) and (d_inicio <= datetime.strptime((g.get('data_recebimento') or g.get('data_registro'))[:10], '%Y-%m-%d').date() <= d_fim)]

    total_ganhos = sum(g['valor'] for g in g_filtrados)
    total_pago = sum(c['valor'] for c in c_filtradas if c['status'] == 'Pago')
    
    pendentes_modal = [c for c in c_filtradas if c['status'] == 'Pendente']
    total_pendente = sum(c['valor'] for c in pendentes_modal)
    
    atrasadas_modal = [c for c in pendentes_modal if datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').date() < hoje]
    total_atrasado = sum(c['valor'] for c in atrasadas_modal)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Recebeu", f"R$ {total_ganhos:.2f}")
    col2.metric("✅ Já Pagou", f"R$ {total_pago:.2f}")
    col3.metric("⏳ A Vencer", f"R$ {total_pendente - total_atrasado:.2f}")
    col4.metric("🔴 Atrasado", f"R$ {total_atrasado:.2f}")
    st.divider()
    
    aba_pend, aba_pag, aba_gan = st.tabs(["🔴 Pendentes", "✅ Pagas", "🟢 Ganhos"])
    with aba_pend:
        for c in pendentes_modal:
            aviso = "⚠️ ATRASADA" if c in atrasadas_modal else ""
            st.write(f"- **{c['descricao']}**: R$ {c['valor']} (Venc: {datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').strftime('%d/%m/%Y')}) {aviso}")
    with aba_pag:
        for c in [c for c in c_filtradas if c['status'] == 'Pago']:
            with st.expander(f"✅ {c['descricao']} - R$ {c['valor']} (Venc: {datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').strftime('%d/%m/%Y')})"):
                if c.get('comprovante'): st.image(c['comprovante'], caption="Comprovante", use_column_width=True)
                else: st.info("Pago sem comprovante anexado.")
    with aba_gan:
        for g in g_filtrados:
            data_str = g.get('data_recebimento') or g.get('data_registro')
            st.write(f"- **{g['descricao']}**: R$ {g['valor']} ({g['frequencia']} - Prev: {datetime.strptime(data_str[:10], '%Y-%m-%d').strftime('%d/%m/%Y')})")

# ==========================================
# 6. INTERFACE PRINCIPAL E ABAS DINÂMICAS
# ==========================================
st.markdown("<h1 style='text-align: center;'><i class='fa-solid fa-wallet'></i> Controle Financeiro Familiar</h1>", unsafe_allow_html=True)
st.divider()

if usuario.get('perfil') == 'admin':
    abas = st.tabs(["📊 Dashboard", "📄 Extrato", "➕ Nova Dívida", "💰 Novo Ganho", "✅ Pagar Conta", "✏️ Editar", "👨‍👩‍👧 Família", "⚙️ Meu Perfil"])
    aba_dash, aba_extrato, aba_divida, aba_ganho, aba_pagar, aba_editar, aba_familia, aba_perfil = abas
else:
    abas = st.tabs(["📊 Meu Painel", "📄 Meu Extrato", "➕ Minha Dívida", "💰 Meu Ganho", "✅ Pagar Conta", "⚙️ Meu Perfil"])
    aba_dash, aba_extrato, aba_divida, aba_ganho, aba_pagar, aba_perfil = abas

# --- ABA 1: DASHBOARD ---
with aba_dash:
    if len(contas_atrasadas) > 0:
        st.error(f"⚠️ Atenção! Existem {len(contas_atrasadas)} conta(s) em atraso pendentes para você!")

    # =======================================================
    # 1. SALDO GLOBAL ABSOLUTO (Livre do Filtro de Datas)
    # =======================================================
    st.markdown("<h3><i class='fa-solid fa-building-columns'></i> Caixa Real (Saldo Global)</h3>", unsafe_allow_html=True)
    st.caption("Dinheiro disponível hoje (Soma de todos os Ganhos - Todas as contas Pagas/Gastos Imediatos).")
    
    col_globais = st.columns(len(dependentes_ativos))
    for index, pessoa in enumerate(dependentes_ativos):
        id_p = pessoa['id']
        
        # Puxa do histórico total (ignorando as datas da barra lateral)
        ganhos_totais = sum(g['valor'] for g in lista_ganhos if g['dependente_id'] == id_p)
        pagos_totais = sum(c['valor'] for c in todas_contas if c['dependente_id'] == id_p and c['status'] == 'Pago')
        
        saldo_real = ganhos_totais - pagos_totais
        
        with col_globais[index]:
            st.metric(
                label=f"💰 {pessoa['nome']}", 
                value=f"R$ {saldo_real:.2f}", 
                delta=f"Entrou: {ganhos_totais:.2f} | Saiu: {pagos_totais:.2f}", 
                delta_color="off"
            )
            
    st.divider()

    # =======================================================
    # 2. RESUMO DO PERÍODO (Afetado pelo Filtro de Datas)
    # =======================================================
    str_inicio = data_inicio.strftime('%d/%m/%Y')
    str_fim = data_fim.strftime('%d/%m/%Y')
    st.markdown(f"<h4><i class='fa-solid fa-file-invoice-dollar'></i> A Pagar no Período <span style='font-size: 0.6em; color: gray;'><i class='fa-regular fa-calendar-days'></i> {str_inicio} a {str_fim}</span></h4>", unsafe_allow_html=True)
    st.caption("Dívidas pendentes apenas dentro das datas filtradas no menu lateral.")
    
    colunas_metricas = st.columns(len(dependentes_ativos))
    for index, pessoa in enumerate(dependentes_ativos):
        nome = pessoa['nome']
        id_pessoa = pessoa['id']
        
        # Usa as variáveis filtradas para mostrar só as contas do mês atual
        devedor = saldos_devedores[id_pessoa] 
        
        with colunas_metricas[index]:
            st.metric(label=f"🔴 Pendente ({nome})", value=f"R$ {devedor:.2f}", delta="Dívidas do mês", delta_color="inverse")
            
            # O botão da janela Modal continua a funcionar perfeitamente
            if st.button("Ver Extrato", key=f"btn_detalhes_{id_pessoa}", use_container_width=True):
                mostrar_detalhes(id_pessoa, nome, data_inicio, data_fim)

    st.divider()

    # =======================================================
    # 3. TERMÔMETRO DO ORÇAMENTO (Meta Familiar do Mês)
    # =======================================================
    # Busca a meta do Supabase (lê a primeira linha da tabela configuracoes)
    try:
        req_meta = supabase.table("configuracoes").select("meta_mensal").execute()
        meta_familia = float(req_meta.data[0]['meta_mensal']) if req_meta.data else 5000.0
    except:
        meta_familia = 5000.0 # Valor de segurança se a tabela não existir ainda
        
    # Soma todas as contas pagas E pendentes do período filtrado
    total_gasto_mes = sum(c['valor'] for c in contas_filtradas) + sum(c['valor'] for c in todas_contas if c['status'] == 'Pago' and c.get('data_vencimento') and data_inicio <= datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').date() <= data_fim)
    # Calcula a porcentagem consumida, travando em 1.0 (100%) para a barra não quebrar o layout
    pct_consumida = total_gasto_mes / meta_familia if meta_familia > 0 else 0
    pct_barra = min(pct_consumida, 1.0)
    
    st.markdown("<h4>🎯 Termômetro de Gastos da Família</h4>", unsafe_allow_html=True)
    
    # Alertas visuais de cor baseados na porcentagem
    if pct_consumida >= 1.0:
        st.error(f"🚨 Orçamento Estourado! Vocês já comprometeram R$ {total_gasto_mes:.2f} da meta de R$ {meta_familia:.2f} ({pct_consumida*100:.1f}%)")
    elif pct_consumida >= 0.8:
        st.warning(f"⚠️ Atenção! Vocês já consumiram {pct_consumida*100:.1f}% da meta mensal. Faltam apenas R$ {meta_familia - total_gasto_mes:.2f} para o teto.")
    else:
        st.success(f"✅ Orçamento Saudável. Vocês consumiram {pct_consumida*100:.1f}% do teto de R$ {meta_familia:.2f}.")
        
    st.progress(pct_barra)
    st.divider()
    
    str_inicio = data_inicio.strftime('%d/%m/%Y')
    
# =======================================================
    # 4. RAIO-X: COMPOSIÇÃO DOS GASTOS
    # =======================================================
    # Junta todas as contas do mês (pendentes e pagas filtradas anteriormente) para analisar o bolo total
    todas_contas_mes = [c for c in contas_filtradas] + [c for c in todas_contas if c['status'] == 'Pago' and c.get('data_vencimento') and data_inicio <= datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').date() <= data_fim]
    
    # Filtra pelo 'carimbo' que criámos na descrição da conta
    gasto_casa = sum(c['valor'] for c in todas_contas_mes if "- Comp." in c['descricao'])
    gasto_individual = sum(c['valor'] for c in todas_contas_mes if "- Comp." not in c['descricao'])
    
    st.write("") # Espaço em branco para deixar o layout respirar
    col_rx1, col_rx2 = st.columns(2)
    
    with col_rx1:
        pct_casa = (gasto_casa / total_gasto_mes * 100) if total_gasto_mes > 0 else 0
        st.markdown(f"**🏢 Despesas da Casa:** R$ {gasto_casa:.2f} <span style='color: gray; font-size: 0.9em;'>( {pct_casa:.1f}% )</span>", unsafe_allow_html=True)
        
    with col_rx2:
        pct_ind = (gasto_individual / total_gasto_mes * 100) if total_gasto_mes > 0 else 0
        st.markdown(f"**👤 Gastos Individuais:** R$ {gasto_individual:.2f} <span style='color: gray; font-size: 0.9em;'>( {pct_ind:.1f}% )</span>", unsafe_allow_html=True)

# --- ABA 2: EXTRATO COMPLETO (COM PROTEÇÃO DE NULOS) ---
with aba_extrato:
    st.subheader("📄 Extrato Financeiro")
    st.write(f"**Período:** {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}")
    
    if usuario.get('perfil') == 'admin':
        opcoes_extrato = [{"id": "todos", "nome": "Todos os Membros (Visão Geral)"}] + lista_dependentes
        alvo_extrato = st.selectbox("Gerar extrato de quem?", opcoes_extrato, format_func=lambda x: x['nome'])
        alvo_id = alvo_extrato['id']
    else:
        alvo_id = usuario['id']
        
    contas_extrato = []
    for c in todas_contas:
        venc_str = c.get('data_vencimento')
        if venc_str and (data_inicio <= datetime.strptime(venc_str[:10], '%Y-%m-%d').date() <= data_fim):
            if alvo_id == "todos" or c['dependente_id'] == alvo_id:
                contas_extrato.append(c)
                
    ganhos_extrato = []
    for g in lista_ganhos:
        reg_str = g.get('data_recebimento') or g.get('data_registro')
        if reg_str and (data_inicio <= datetime.strptime(reg_str[:10], '%Y-%m-%d').date() <= data_fim):
            if alvo_id == "todos" or g['dependente_id'] == alvo_id:
                ganhos_extrato.append(g)
                
    tot_ganhos = sum(g['valor'] for g in ganhos_extrato)
    tot_pagos = sum(c['valor'] for c in contas_extrato if c['status'] == 'Pago')
    tot_pendentes = sum(c['valor'] for c in contas_extrato if c['status'] == 'Pendente')
    saldo_periodo = tot_ganhos - tot_pagos
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entradas (Ganhos)", f"R$ {tot_ganhos:.2f}")
    c2.metric("Saídas (Pagas)", f"R$ {tot_pagos:.2f}")
    c3.metric("Saldo do Período", f"R$ {saldo_periodo:.2f}")
    c4.metric("A Pagar (Pendentes)", f"R$ {tot_pendentes:.2f}")
    
    st.divider()
    
    st.write("#### 🟢 Entradas Registradas")
    if ganhos_extrato:
        df_ganhos = pd.DataFrame(ganhos_extrato)
        df_ganhos['Membro'] = df_ganhos['dependente_id'].map(id_para_nome)
        # Proteção contra erros Type Error (Transforma Nulo numa data padrão segura)
        df_ganhos['Data'] = df_ganhos.apply(lambda x: str(x.get('data_recebimento') or x.get('data_registro') or hoje.isoformat())[:10], axis=1)
        df_ganhos['Data'] = pd.to_datetime(df_ganhos['Data']).dt.strftime('%d/%m/%Y')
        df_g_show = df_ganhos[['Data', 'Membro', 'descricao', 'frequencia', 'valor']].copy()
        df_g_show.columns = ['Data', 'Membro', 'Descrição', 'Frequência', 'Valor (R$)']
        st.dataframe(df_g_show, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma entrada neste período.")
        
    st.write("#### 🔴 Saídas e Dívidas")
    if contas_extrato:
        df_contas = pd.DataFrame(contas_extrato)
        df_contas['Membro'] = df_contas['dependente_id'].map(id_para_nome)
        df_contas['Data'] = df_contas['data_vencimento'].apply(lambda x: str(x)[:10] if pd.notnull(x) else hoje.isoformat()[:10])
        df_contas['Data'] = pd.to_datetime(df_contas['Data']).dt.strftime('%d/%m/%Y')
        df_c_show = df_contas[['Data', 'Membro', 'descricao', 'status', 'valor']].copy()
        df_c_show.columns = ['Vencimento', 'Membro', 'Descrição', 'Status', 'Valor (R$)']
        st.dataframe(df_c_show, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma dívida neste período.")

# --- ABA 3: REGISTRAR SAÍDA (GASTOS IMEDIATOS OU DÍVIDAS) ---
with aba_divida:
    st.subheader("🧾 Registrar Saída")
    
    if 'msg_sucesso_divida' in st.session_state:
        st.success(st.session_state.msg_sucesso_divida)
        del st.session_state.msg_sucesso_divida

    def adicionar_meses(data_orig, meses):
        mes = data_orig.month - 1 + meses
        ano = data_orig.year + mes // 12
        mes = mes % 12 + 1
        dia = min(data_orig.day, [31,29 if ano%4==0 and not ano%400==0 else 28,31,30,31,30,31,31,30,31,30,31][mes-1])
        return date(ano, mes, dia)

    # --- NOVO: Seletor de Tipo de Gasto ---
    tipo_gasto = st.radio(
        "Tipo de Registro:", 
        ["Gasto Imediato (Já pago no dia a dia)", "Conta a Pagar (Futura / Parcelada)"], 
        horizontal=True, 
        key="div_tipo_gasto"
    )
    st.divider()

    if usuario.get('perfil') == 'admin':
        tipo_conta = st.radio("Divisão:", ["Individual", "Compartilhada"], key="div_tipo")
        quem_paga = st.selectbox("De quem é a saída?", [p["nome"] for p in lista_dependentes], key="div_quem")
    else:
        tipo_conta = "Individual"
        quem_paga = usuario['nome']
        st.info(f"Registando saída para: **{quem_paga}**")
        
    descricao = st.text_input("O que foi pago/comprado?", key="div_desc")
    valor_parcela = st.number_input("Valor Total (R$):", min_value=0.0, key="div_val")
    
    divisoes = {}
    if tipo_conta == "Compartilhada":
        st.markdown("#### ⚖️ Divisão da Conta (%)")
        st.caption("A soma de todos deve dar 100%.")
        colunas_div = st.columns(len(lista_dependentes))
        pct_padrao = 100.0 / len(lista_dependentes) if len(lista_dependentes) > 0 else 100.0
        
        for idx, p in enumerate(lista_dependentes):
            with colunas_div[idx]:
                divisoes[p['id']] = st.number_input(f"{p['nome'][:6]}", min_value=0.0, max_value=100.0, value=pct_padrao, step=1.0, key=f"div_pct_{p['id']}")
                
    # --- LÓGICA CONDICIONAL DO FORMULÁRIO ---
    if tipo_gasto == "Conta a Pagar (Futura / Parcelada)":
        col_data1, col_data2 = st.columns(2)
        with col_data1: is_parcelado = st.checkbox("É parcelado?", key="div_parc")
        with col_data2: 
            if is_parcelado:
                qtd_parcelas = st.number_input("Vezes:", min_value=2, value=2, key="div_qtd")
            else:
                qtd_parcelas = 1
        data_vencimento = st.date_input("Vencimento 1ª Parcela:", value=hoje, key="div_venc")
        status_registro = "Pendente"
    else:
        # Modo Gasto Imediato: Esconde parcelas e datas, assume Hoje e Pago.
        qtd_parcelas = 1
        data_vencimento = hoje
        status_registro = "Pago"
        st.info("💡 Como é um gasto imediato (ex: almoço, padaria), o sistema salvará com a data de hoje e status já constará como 'Pago' automaticamente.")
    
    if st.button("Salvar Registro", type="primary"):
        if tipo_conta == "Compartilhada" and abs(sum(divisoes.values()) - 100.0) > 0.1:
            st.error(f"❌ A soma das porcentagens deve ser 100%! Atualmente está em {sum(divisoes.values()):.1f}%.")
        elif not descricao or valor_parcela <= 0:
            st.warning("⚠️ Preencha a descrição e o valor antes de salvar!")
        else:
            id_pessoa = next(p["id"] for p in lista_dependentes if p["nome"] == quem_paga)
            pacote = []
            for i in range(qtd_parcelas):
                venc = adicionar_meses(data_vencimento, i)
                mes_ref = f"{venc.month:02d}/{venc.year}"
                
                # Deixa a descrição limpa se não for parcelado
                desc_final = f"{descricao} ({i+1}/{qtd_parcelas})" if qtd_parcelas > 1 else descricao
                
                if tipo_conta == "Individual":
                    pacote.append({"dependente_id": id_pessoa, "descricao": desc_final, "valor": valor_parcela, "mes": mes_ref, "data_vencimento": venc.isoformat(), "status": status_registro})
                elif tipo_conta == "Compartilhada":
                    desc_comp = f"{desc_final} - Comp."
                    for p_id, pct in divisoes.items():
                        if pct > 0:
                            pacote.append({"dependente_id": p_id, "descricao": desc_comp, "valor": round(valor_parcela * (pct / 100.0), 2), "mes": mes_ref, "data_vencimento": venc.isoformat(), "status": status_registro})
                            
            supabase.table("acertos_cartao").insert(pacote).execute()
            
            # Mensagem inteligente baseada no tipo escolhido
            st.session_state.msg_sucesso_divida = f"✅ {'Gasto imediato registrado' if status_registro == 'Pago' else 'Conta a pagar salva'} com sucesso!"
            
            chaves_para_limpar = ["div_desc", "div_val", "div_parc", "div_qtd", "div_venc", "div_tipo", "div_quem", "div_tipo_gasto"]
            for p in lista_dependentes: chaves_para_limpar.append(f"div_pct_{p['id']}")
            for chave in chaves_para_limpar:
                if chave in st.session_state: del st.session_state[chave]
                    
            st.rerun()

# --- ABA 4: NOVO GANHO ---
with aba_ganho:
    st.subheader("💰 Registrar Recebimento")
    with st.form("form_ganhos"):
        if usuario.get('perfil') == 'admin':
            quem_recebeu = st.selectbox("Para quem?", [p["nome"] for p in lista_dependentes])
        else:
            quem_recebeu = usuario['nome']
            st.info(f"Registando Ganho para: **{quem_recebeu}**")
            
        descricao_ganho = st.text_input("Origem")
        valor_ganho = st.number_input("Valor (R$)?", min_value=0.0)
        col_freq, col_data = st.columns(2)
        with col_freq: frequencia = st.selectbox("Frequência?", ["Mensal", "Quinzenal", "Semanal", "Único"])
        with col_data: data_recebimento = st.date_input("Data prevista:", value=hoje)
        
        if st.form_submit_button("Salvar Recebimento", type="primary"):
            id_pessoa = next(p["id"] for p in lista_dependentes if p["nome"] == quem_recebeu)
            supabase.table("ganhos").insert({"dependente_id": id_pessoa, "descricao": descricao_ganho, "valor": valor_ganho, "frequencia": frequencia, "data_recebimento": data_recebimento.isoformat()}).execute()
            st.success("Salvo!")
            st.rerun()

# --- ABA 5: PAGAR CONTA (COM COMPROVATIVO) ---
with aba_pagar:
    st.subheader("✅ Baixa em Contas")
    minhas_pendentes = contas_pendentes if usuario.get('perfil') == 'admin' else [c for c in contas_pendentes if c['dependente_id'] == usuario['id']]
    
    if not minhas_pendentes: st.success("Tudo pago por aqui!")
    else:
        with st.form("form_pagar"):
            def fmt_conta(c):
                atr = " ⚠️[ATRASADA]" if c.get('data_vencimento') and datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').date() < hoje else ""
                v = datetime.strptime(c['data_vencimento'][:10], '%Y-%m-%d').strftime('%d/%m/%Y') if c.get('data_vencimento') else "Sem data"
                return f"{id_para_nome.get(c['dependente_id'])} | {c['descricao']} | R$ {c['valor']} | Venc: {v}{atr}"
            
            conta_escolhida = st.selectbox("Selecione a conta para pagar:", minhas_pendentes, format_func=fmt_conta)
            comprovante_file = st.file_uploader("Anexar Comprovante (Imagem Opcional)", type=['png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("Confirmar Pagamento", type="primary"):
                dados_update = {"status": "Pago"}
                if comprovante_file is not None:
                    bytes_data = comprovante_file.getvalue()
                    b64_string = base64.b64encode(bytes_data).decode()
                    dados_update["comprovante"] = f"data:{comprovante_file.type};base64,{b64_string}"
                    
                supabase.table("acertos_cartao").update(dados_update).eq("id", conta_escolhida['id']).execute()
                st.success("Conta Paga!")
                st.rerun()

# --- ABA 6: MEU PERFIL (TROCAR SENHA) ---
with aba_perfil:
    st.subheader("⚙️ Meu Perfil e Segurança")
    st.write("Altere a sua senha de acesso ao sistema.")
    with st.form("form_senha"):
        senha_atual = st.text_input("Senha Atual:", type="password")
        nova_senha = st.text_input("Nova Senha:", type="password")
        confirma_senha = st.text_input("Confirme a Nova Senha:", type="password")
        
        if st.form_submit_button("Mudar Senha", type="primary"):
            if senha_atual != usuario.get('senha'): st.error("A senha atual está incorreta!")
            elif nova_senha != confirma_senha: st.error("As novas senhas não coincidem!")
            elif len(nova_senha) < 4: st.error("A nova senha deve ter pelo menos 4 caracteres.")
            else:
                supabase.table("dependentes").update({"senha": nova_senha}).eq("id", usuario['id']).execute()
                st.session_state.usuario_logado['senha'] = nova_senha 
                st.success("Senha alterada com sucesso!")

# --- ABAS RESTRITAS APENAS PARA ADMIN ---
if usuario.get('perfil') == 'admin':
    with aba_editar:
        st.subheader("✏️ Editar ou Excluir Histórico")
        sub_d, sub_g, sub_opt = st.tabs(["🔴 Dívidas", "🟢 Ganhos", "⚙️ Opções"])
        
        with sub_d:
            if todas_contas:
                with st.form("form_edit_d"):
                    d_sel = st.selectbox("Selecione a Conta:", todas_contas, format_func=lambda c: f"{id_para_nome.get(c['dependente_id'])} | {c['descricao']} | R$ {c['valor']} | Status: {c['status']}")
                    
                    n_desc = st.text_input("Descrição:", value=d_sel['descricao'])
                    n_val = st.number_input("Valor (R$):", min_value=0.0, value=float(d_sel['valor']))
                    
                    # --- NOVO: Campo para alterar o Status diretamente ---
                    status_atual = d_sel.get('status', 'Pendente')
                    n_status = st.selectbox("Status:", ["Pendente", "Pago"], index=0 if status_atual == 'Pendente' else 1)
                    
                    venc_atual = d_sel.get('data_vencimento')
                    data_padrao = datetime.strptime(venc_atual[:10], '%Y-%m-%d').date() if venc_atual else hoje
                    n_venc = st.date_input("Vencimento:", value=data_padrao)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        btn_atualizar = st.form_submit_button("Atualizar Conta", type="primary", use_container_width=True)
                    with col_btn2:
                        btn_excluir = st.form_submit_button("❌ Excluir Conta", use_container_width=True)
                        
                    if btn_atualizar:
                        # O n_status foi adicionado na atualização do banco
                        supabase.table("acertos_cartao").update({
                            "descricao": n_desc, 
                            "valor": n_val, 
                            "status": n_status, 
                            "data_vencimento": n_venc.isoformat()
                        }).eq("id", d_sel['id']).execute()
                        
                        st.success("Conta atualizada com sucesso!")
                        st.rerun()
                    elif btn_excluir:
                        supabase.table("acertos_cartao").delete().eq("id", d_sel['id']).execute()
                        st.warning("Conta excluída permanentemente!")
                        st.rerun()
            else: 
                st.info("Nenhuma dívida registada para editar.")

        # --- NOVO: Aba de Opções para o Admin mudar a Meta ---
        with sub_opt:
            st.write("Configurações Globais do Sistema")
            with st.form("form_meta"):
                try:
                    meta_atual = float(supabase.table("configuracoes").select("meta_mensal").execute().data[0]['meta_mensal'])
                except:
                    meta_atual = 5000.0
                    
                nova_meta = st.number_input("Teto de Gastos Mensal da Família (R$):", min_value=0.0, value=meta_atual)
                
                if st.form_submit_button("Atualizar Meta"):
                    # O Supabase usa eq('id', 1) assumindo que você criou a primeira linha
                    supabase.table("configuracoes").update({"meta_mensal": nova_meta}).eq("id", 1).execute()
                    st.success("Teto de gastos atualizado!")
                    st.rerun()

