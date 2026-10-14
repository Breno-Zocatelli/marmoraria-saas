"""
Backend REST API & Banco de Dados Centralizado - Marmoraria Marmobraz SaaS (Etapa 4)
Armazenamento relacional e persistente com SQLite + FastAPI
"""
import os
import json
import sqlite3
from datetime import datetime
from typing import List, Optional, Any, Dict
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(
    title="Marmoraria Marmobraz SaaS API",
    description="API centralizada em nuvem para orçamentos, catálogo e fila de fábrica em tempo real",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caminho do banco de dados e arquivos estáticos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(DATA_DIR, "marmoraria.db"))

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
INDEX_PATH = os.path.join(FRONTEND_DIR, "index.html")
if not os.path.exists(INDEX_PATH):
    INDEX_PATH = os.path.join(BASE_DIR, "index.html")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabela principal de Orçamentos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orcamentos (
        id TEXT PRIMARY KEY,
        numero TEXT,
        status TEXT,
        cliente_nome TEXT,
        cliente_fone TEXT,
        tipo_entrega TEXT,
        total_prazo REAL DEFAULT 0.0,
        total_vista REAL DEFAULT 0.0,
        m2_total REAL DEFAULT 0.0,
        data_criacao TEXT,
        vendedor TEXT,
        dados_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Tabela de Catálogos (materiais, cubas, acabamentos, regras_lados, modalidades_logistica)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS catalogos (
        tipo TEXT PRIMARY KEY,
        dados_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Tabela de Clientes & CRM (Passo 3)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        fone TEXT,
        endereco TEXT,
        ponto_ref TEXT,
        cidade TEXT,
        tipo TEXT DEFAULT 'consumidor',
        observacoes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Tabela de Agenda & Prazos (Passo 4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agenda (
        id TEXT PRIMARY KEY,
        orcamento_id TEXT,
        cliente_nome TEXT NOT NULL,
        cliente_fone TEXT,
        endereco TEXT,
        tipo TEXT NOT NULL, -- 'medicao' ou 'instalacao'
        data TEXT NOT NULL, -- YYYY-MM-DD
        turno TEXT DEFAULT 'comercial', -- 'manha', 'tarde', 'comercial'
        responsavel TEXT,
        status TEXT DEFAULT 'agendado', -- 'agendado', 'realizado', 'cancelado'
        observacoes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Tabela de Contas Bancárias & Caixas (Módulo Financeiro)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bancos (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        tipo TEXT DEFAULT 'corrente',
        agencia TEXT,
        conta TEXT,
        titular TEXT,
        cor TEXT DEFAULT '#0284c7',
        saldo_inicial REAL DEFAULT 0.0,
        padrao INTEGER DEFAULT 0,
        ativo INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Seed inicial de bancos se estiver vazio
    cursor.execute("SELECT COUNT(*) as total FROM bancos;")
    if cursor.fetchone()["total"] == 0:
        agora = datetime.now().isoformat()
        cursor.executemany("""
        INSERT INTO bancos (id, nome, tipo, agencia, conta, titular, cor, saldo_inicial, padrao, ativo, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [
            ("banco_itau", "Banco Itaú PJ", "corrente", "1234", "56789-0", "Marmoraria Marmobraz Ltda", "#f97316", 0.0, 1, 1, agora, agora),
            ("banco_sicoob", "Sicoob Cooperativa", "corrente", "3040", "12890-1", "Marmoraria Marmobraz Ltda", "#0284c7", 0.0, 0, 1, agora, agora),
            ("banco_caixa_fisico", "Caixa Físico / Gaveta", "carteira_fisica", "-", "-", "Balcão da Marmoraria", "#10b981", 0.0, 0, 1, agora, agora)
        ])

    conn.commit()
    conn.close()

# Inicializa banco de dados ao carregar
init_db()

# --- MODELOS PYDANTIC ---
class StatusUpdateRequest(BaseModel):
    status: str

# --- ENDPOINTS DA API ---

@app.get("/api/health")
def health_check():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM orcamentos;")
    total_orc = cursor.fetchone()["total"]
    conn.close()
    return {
        "status": "online",
        "app": "Marmoraria Marmobraz SaaS",
        "database": "sqlite",
        "db_path": DB_PATH,
        "total_orcamentos": total_orc,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/orcamentos")
def listar_orcamentos(status: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    if status and status != "todos":
        cursor.execute("SELECT dados_json FROM orcamentos WHERE status = ? ORDER BY updated_at DESC;", (status,))
    else:
        cursor.execute("SELECT dados_json FROM orcamentos ORDER BY updated_at DESC;")
    
    rows = cursor.fetchall()
    conn.close()
    
    lista = []
    for r in rows:
        try:
            lista.append(json.loads(r["dados_json"]))
        except Exception:
            pass
    return lista

@app.get("/api/orcamentos/{orcamento_id}")
def obter_orcamento(orcamento_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT dados_json FROM orcamentos WHERE id = ?;", (orcamento_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    return json.loads(row["dados_json"])

@app.post("/api/orcamentos")
def salvar_orcamento(orcamento: Dict[str, Any] = Body(...)):
    orc_id = str(orcamento.get("id") or f"orc_{int(datetime.now().timestamp() * 1000)}")
    orcamento["id"] = orc_id
    
    numero = str(orcamento.get("numero") or "ORC-000")
    status = str(orcamento.get("status") or "em_aberto")
    cliente_nome = str(orcamento.get("clienteNome") or "")
    cliente_fone = str(orcamento.get("clienteFone") or "")
    tipo_entrega = str(orcamento.get("tipoEntrega") or "entregar")
    vendedor = str(orcamento.get("vendedor") or "")
    data_criacao = str(orcamento.get("dataCriacao") or datetime.now().strftime("%d/%m/%Y"))
    
    total_prazo = float(orcamento.get("totalPrazo") or 0.0)
    total_vista = float(orcamento.get("totalVista") or 0.0)
    m2_total = float(orcamento.get("m2Total") or 0.0)
    
    agora_iso = datetime.now().isoformat()
    orcamento["updatedAt"] = agora_iso
    dados_json = json.dumps(orcamento, ensure_ascii=False)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verifica se já existe para preservar created_at
    cursor.execute("SELECT created_at FROM orcamentos WHERE id = ?;", (orc_id,))
    existente = cursor.fetchone()
    created_at = existente["created_at"] if existente else agora_iso
    
    cursor.execute("""
    INSERT INTO orcamentos (
        id, numero, status, cliente_nome, cliente_fone, tipo_entrega,
        total_prazo, total_vista, m2_total, data_criacao, vendedor,
        dados_json, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        numero = excluded.numero,
        status = excluded.status,
        cliente_nome = excluded.cliente_nome,
        cliente_fone = excluded.cliente_fone,
        tipo_entrega = excluded.tipo_entrega,
        total_prazo = excluded.total_prazo,
        total_vista = excluded.total_vista,
        m2_total = excluded.m2_total,
        vendedor = excluded.vendedor,
        dados_json = excluded.dados_json,
        updated_at = excluded.updated_at;
    """, (
        orc_id, numero, status, cliente_nome, cliente_fone, tipo_entrega,
        total_prazo, total_vista, m2_total, data_criacao, vendedor,
        dados_json, created_at, agora_iso
    ))
    
    conn.commit()
    conn.close()
    return orcamento

@app.put("/api/orcamentos/{orcamento_id}/status")
def atualizar_status(orcamento_id: str, body: StatusUpdateRequest):
    novo_status = body.status
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT dados_json FROM orcamentos WHERE id = ?;", (orcamento_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    
    orcamento = json.loads(row["dados_json"])
    orcamento["status"] = novo_status
    agora_iso = datetime.now().isoformat()
    orcamento["updatedAt"] = agora_iso
    dados_json = json.dumps(orcamento, ensure_ascii=False)
    
    cursor.execute("""
    UPDATE orcamentos SET status = ?, dados_json = ?, updated_at = ? WHERE id = ?;
    """, (novo_status, dados_json, agora_iso, orcamento_id))
    
    conn.commit()
    conn.close()
    return orcamento

@app.delete("/api/orcamentos/{orcamento_id}")
def excluir_orcamento(orcamento_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orcamentos WHERE id = ?;", (orcamento_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": orcamento_id}

@app.get("/api/catalogos")
def obter_todos_catalogos():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT tipo, dados_json FROM catalogos;")
    rows = cursor.fetchall()
    conn.close()
    
    resultado = {}
    for r in rows:
        try:
            resultado[r["tipo"]] = json.loads(r["dados_json"])
        except Exception:
            pass
    return resultado

@app.get("/api/catalogos/{tipo}")
def obter_catalogo(tipo: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT dados_json FROM catalogos WHERE tipo = ?;", (tipo,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return []
    return json.loads(row["dados_json"])

@app.post("/api/catalogos/{tipo}")
def salvar_catalogo(tipo: str, itens: List[Dict[str, Any]] = Body(...)):
    agora_iso = datetime.now().isoformat()
    dados_json = json.dumps(itens, ensure_ascii=False)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO catalogos (tipo, dados_json, updated_at)
    VALUES (?, ?, ?)
    ON CONFLICT(tipo) DO UPDATE SET
        dados_json = excluded.dados_json,
        updated_at = excluded.updated_at;
    """, (tipo, dados_json, agora_iso))
    
    conn.commit()
    conn.close()
    return {"status": "ok", "tipo": tipo, "count": len(itens)}

# --- ENDPOINTS DE CLIENTES (CRM / PASSO 3) ---

@app.get("/api/clientes")
def listar_clientes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes ORDER BY nome ASC;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/clientes")
def salvar_cliente(cliente: Dict[str, Any] = Body(...)):
    c_id = str(cliente.get("id") or f"cli_{int(datetime.now().timestamp() * 1000)}")
    nome = str(cliente.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome do cliente é obrigatório")
    
    fone = str(cliente.get("fone") or "").strip()
    endereco = str(cliente.get("endereco") or "").strip()
    ponto_ref = str(cliente.get("pontoRef") or cliente.get("ponto_ref") or "").strip()
    cidade = str(cliente.get("cidade") or "").strip()
    tipo = str(cliente.get("tipo") or "consumidor").strip()
    observacoes = str(cliente.get("observacoes") or "").strip()
    agora_iso = datetime.now().isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM clientes WHERE id = ?;", (c_id,))
    existente = cursor.fetchone()
    created_at = existente["created_at"] if existente else agora_iso
    
    cursor.execute("""
    INSERT INTO clientes (id, nome, fone, endereco, ponto_ref, cidade, tipo, observacoes, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        nome = excluded.nome,
        fone = excluded.fone,
        endereco = excluded.endereco,
        ponto_ref = excluded.ponto_ref,
        cidade = excluded.cidade,
        tipo = excluded.tipo,
        observacoes = excluded.observacoes,
        updated_at = excluded.updated_at;
    """, (c_id, nome, fone, endereco, ponto_ref, cidade, tipo, observacoes, created_at, agora_iso))
    
    conn.commit()
    conn.close()
    
    cliente["id"] = c_id
    cliente["createdAt"] = created_at
    cliente["updatedAt"] = agora_iso
    return cliente

@app.delete("/api/clientes/{cliente_id}")
def excluir_cliente(cliente_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE id = ?;", (cliente_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": cliente_id}

# --- ENDPOINTS DE AGENDA & PRAZOS (PASSO 4) ---

@app.get("/api/agenda")
def listar_agenda(status: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    if status and status != "todos":
        cursor.execute("SELECT * FROM agenda WHERE status = ? ORDER BY data ASC, created_at ASC;", (status,))
    else:
        cursor.execute("SELECT * FROM agenda ORDER BY data ASC, created_at ASC;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/agenda")
def salvar_evento_agenda(evento: Dict[str, Any] = Body(...)):
    e_id = str(evento.get("id") or f"age_{int(datetime.now().timestamp() * 1000)}")
    orc_id = str(evento.get("orcamentoId") or evento.get("orcamento_id") or "").strip()
    cliente_nome = str(evento.get("clienteNome") or evento.get("cliente_nome") or "").strip()
    if not cliente_nome:
        raise HTTPException(status_code=400, detail="Nome do cliente é obrigatório")
    
    cliente_fone = str(evento.get("clienteFone") or evento.get("cliente_fone") or "").strip()
    endereco = str(evento.get("endereco") or "").strip()
    tipo = str(evento.get("tipo") or "medicao").strip()
    data = str(evento.get("data") or datetime.now().strftime("%Y-%m-%d")).strip()
    turno = str(evento.get("turno") or "comercial").strip()
    responsavel = str(evento.get("responsavel") or "").strip()
    status = str(evento.get("status") or "agendado").strip()
    observacoes = str(evento.get("observacoes") or "").strip()
    agora_iso = datetime.now().isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM agenda WHERE id = ?;", (e_id,))
    existente = cursor.fetchone()
    created_at = existente["created_at"] if existente else agora_iso
    
    cursor.execute("""
    INSERT INTO agenda (id, orcamento_id, cliente_nome, cliente_fone, endereco, tipo, data, turno, responsavel, status, observacoes, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        orcamento_id = excluded.orcamento_id,
        cliente_nome = excluded.cliente_nome,
        cliente_fone = excluded.cliente_fone,
        endereco = excluded.endereco,
        tipo = excluded.tipo,
        data = excluded.data,
        turno = excluded.turno,
        responsavel = excluded.responsavel,
        status = excluded.status,
        observacoes = excluded.observacoes,
        updated_at = excluded.updated_at;
    """, (e_id, orc_id, cliente_nome, cliente_fone, endereco, tipo, data, turno, responsavel, status, observacoes, created_at, agora_iso))
    
    conn.commit()
    conn.close()
    
    evento["id"] = e_id
    evento["createdAt"] = created_at
    evento["updatedAt"] = agora_iso
    return evento

@app.delete("/api/agenda/{evento_id}")
def excluir_evento_agenda(evento_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agenda WHERE id = ?;", (evento_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": evento_id}

# --- ENDPOINTS DE BANCOS & CONTAS BANCÁRIAS (MÓDULO FINANCEIRO) ---

@app.get("/api/bancos")
def listar_bancos():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bancos WHERE ativo = 1 ORDER BY padrao DESC, nome ASC;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/bancos")
def salvar_banco(banco: Dict[str, Any] = Body(...)):
    b_id = str(banco.get("id") or f"banco_{int(datetime.now().timestamp() * 1000)}").strip()
    nome = str(banco.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome do banco/conta é obrigatório")
    
    tipo = str(banco.get("tipo") or "corrente").strip()
    agencia = str(banco.get("agencia") or "").strip()
    conta = str(banco.get("conta") or "").strip()
    titular = str(banco.get("titular") or "").strip()
    cor = str(banco.get("cor") or "#0284c7").strip()
    saldo_inicial = float(banco.get("saldoInicial") or banco.get("saldo_inicial") or 0.0)
    padrao = 1 if banco.get("padrao") else 0
    ativo = 1 if banco.get("ativo", True) else 0
    agora_iso = datetime.now().isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Se este banco for padrão, desmarca padrão dos outros
    if padrao == 1:
        cursor.execute("UPDATE bancos SET padrao = 0;")
        
    cursor.execute("SELECT created_at FROM bancos WHERE id = ?;", (b_id,))
    existente = cursor.fetchone()
    created_at = existente["created_at"] if existente else agora_iso
    
    cursor.execute("""
    INSERT INTO bancos (id, nome, tipo, agencia, conta, titular, cor, saldo_inicial, padrao, ativo, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        nome = excluded.nome,
        tipo = excluded.tipo,
        agencia = excluded.agencia,
        conta = excluded.conta,
        titular = excluded.titular,
        cor = excluded.cor,
        saldo_inicial = excluded.saldo_inicial,
        padrao = excluded.padrao,
        ativo = excluded.ativo,
        updated_at = excluded.updated_at;
    """, (b_id, nome, tipo, agencia, conta, titular, cor, saldo_inicial, padrao, ativo, created_at, agora_iso))
    
    conn.commit()
    conn.close()
    
    banco["id"] = b_id
    banco["padrao"] = bool(padrao)
    banco["ativo"] = bool(ativo)
    banco["createdAt"] = created_at
    banco["updatedAt"] = agora_iso
    return banco

@app.delete("/api/bancos/{banco_id}")
def excluir_banco(banco_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bancos WHERE id = ?;", (banco_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": banco_id}

@app.post("/api/sync")
def sincronizar_dados(payload: Dict[str, Any] = Body(...)):
    """
    Sincronização bidirecional inteligente:
    - Mescla orçamentos enviados pelo cliente com os da nuvem.
    - Sincroniza catálogo e base de clientes CRM.
    - Se a nuvem estiver vazia, salva os locais.
    - Retorna a lista consolidada atualizada.
    """
    orcamentos_locais = payload.get("orcamentos") or []
    catalogos_locais = payload.get("catalogos") or {}
    clientes_locais = payload.get("clientes") or []
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Sincroniza orçamentos locais se a nuvem estiver sem aquele orçamento
    for orc in orcamentos_locais:
        orc_id = orc.get("id")
        if not orc_id:
            continue
        cursor.execute("SELECT id FROM orcamentos WHERE id = ?;", (orc_id,))
        if not cursor.fetchone():
            agora = datetime.now().isoformat()
            cursor.execute("""
            INSERT INTO orcamentos (
                id, numero, status, cliente_nome, cliente_fone, tipo_entrega,
                total_prazo, total_vista, m2_total, data_criacao, vendedor,
                dados_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                orc_id,
                orc.get("numero", "ORC"),
                orc.get("status", "em_aberto"),
                orc.get("clienteNome", ""),
                orc.get("clienteFone", ""),
                orc.get("tipoEntrega", "entregar"),
                float(orc.get("totalPrazo") or 0.0),
                float(orc.get("totalVista") or 0.0),
                float(orc.get("m2Total") or 0.0),
                orc.get("dataCriacao", ""),
                orc.get("vendedor", ""),
                json.dumps(orc, ensure_ascii=False),
                agora,
                agora
            ))
    
    # 2. Sincroniza catálogos se banco estiver vazio para algum tipo
    for tipo, itens in catalogos_locais.items():
        if not itens:
            continue
        cursor.execute("SELECT tipo FROM catalogos WHERE tipo = ?;", (tipo,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO catalogos (tipo, dados_json, updated_at) VALUES (?, ?, ?);
            """, (tipo, json.dumps(itens, ensure_ascii=False), datetime.now().isoformat()))
    
    # 3. Sincroniza clientes CRM locais se a nuvem não possuir
    for cli in clientes_locais:
        c_id = cli.get("id")
        if not c_id:
            continue
        cursor.execute("SELECT id FROM clientes WHERE id = ?;", (c_id,))
        if not cursor.fetchone():
            agora = datetime.now().isoformat()
            cursor.execute("""
            INSERT INTO clientes (id, nome, fone, endereco, ponto_ref, cidade, tipo, observacoes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                c_id,
                cli.get("nome", ""),
                cli.get("fone", ""),
                cli.get("endereco", ""),
                cli.get("pontoRef", "") or cli.get("ponto_ref", ""),
                cli.get("cidade", ""),
                cli.get("tipo", "consumidor"),
                cli.get("observacoes", ""),
                agora,
                agora
            ))
    
    # 4. Auto-seed de clientes a partir de orçamentos existentes caso tabela esteja vazia
    cursor.execute("SELECT COUNT(*) as total FROM clientes;")
    if cursor.fetchone()["total"] == 0:
        cursor.execute("SELECT DISTINCT cliente_nome, cliente_fone, dados_json FROM orcamentos WHERE cliente_nome != '';")
        for row in cursor.fetchall():
            c_nome = (row["cliente_nome"] or "").strip()
            c_fone = (row["cliente_fone"] or "").strip()
            if not c_nome or c_nome in ["Novo Cliente", "Cliente Sem Nome"]:
                continue
            cursor.execute("SELECT id FROM clientes WHERE nome = ?;", (c_nome,))
            if cursor.fetchone():
                continue
            try:
                d = json.loads(row["dados_json"])
                end = d.get("clienteEndereco", "")
                pref = d.get("clientePontoRef", "")
            except Exception:
                end, pref = "", ""
            c_id = f"cli_{abs(hash(c_nome + c_fone))}"
            agora = datetime.now().isoformat()
            cursor.execute("""
            INSERT INTO clientes (id, nome, fone, endereco, ponto_ref, cidade, tipo, observacoes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (c_id, c_nome, c_fone, end, pref, "", "consumidor", "Importado automaticamente", agora, agora))
    
    agenda_locais = payload.get("agenda") or []
    for item in agenda_locais:
        a_id = item.get("id")
        if not a_id:
            continue
        cursor.execute("SELECT id FROM agenda WHERE id = ?;", (a_id,))
        if not cursor.fetchone():
            agora = datetime.now().isoformat()
            cursor.execute("""
            INSERT INTO agenda (id, orcamento_id, cliente_nome, cliente_fone, endereco, tipo, data, turno, responsavel, status, observacoes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                a_id,
                item.get("orcamentoId") or item.get("orcamento_id") or "",
                item.get("clienteNome") or item.get("cliente_nome") or "",
                item.get("clienteFone") or item.get("cliente_fone") or "",
                item.get("endereco") or "",
                item.get("tipo") or "medicao",
                item.get("data") or agora[:10],
                item.get("turno") or "comercial",
                item.get("responsavel") or "",
                item.get("status") or "agendado",
                item.get("observacoes") or "",
                agora,
                agora
            ))
            
    # 5. Processa exclusões e sincroniza contas bancárias
    bancos_excluidos = payload.get("bancos_excluidos") or []
    for b_del in bancos_excluidos:
        cursor.execute("DELETE FROM bancos WHERE id = ?;", (b_del,))

    bancos_locais = payload.get("bancos") or []
    for b in bancos_locais:
        b_id = b.get("id")
        if not b_id or b_id in bancos_excluidos:
            continue
        cursor.execute("SELECT id FROM bancos WHERE id = ?;", (b_id,))
        if not cursor.fetchone():
            agora = datetime.now().isoformat()
            cursor.execute("""
            INSERT INTO bancos (id, nome, tipo, agencia, conta, titular, cor, saldo_inicial, padrao, ativo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                b_id,
                b.get("nome", ""),
                b.get("tipo", "corrente"),
                b.get("agencia", ""),
                b.get("conta", ""),
                b.get("titular", ""),
                b.get("cor", "#0284c7"),
                float(b.get("saldoInicial") or b.get("saldo_inicial") or 0.0),
                1 if b.get("padrao") else 0,
                1 if b.get("ativo", True) else 0,
                agora,
                agora
            ))
    
    conn.commit()
    
    # 6. Carrega estado canônico completo do banco para devolver ao cliente
    cursor.execute("SELECT dados_json FROM orcamentos ORDER BY updated_at DESC;")
    todos_orc = [json.loads(r["dados_json"]) for r in cursor.fetchall()]
    
    cursor.execute("SELECT tipo, dados_json FROM catalogos;")
    todos_cat = {}
    for r in cursor.fetchall():
        try:
            todos_cat[r["tipo"]] = json.loads(r["dados_json"])
        except Exception:
            pass
            
    cursor.execute("SELECT * FROM clientes ORDER BY nome ASC;")
    todos_cli = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM agenda ORDER BY data ASC, created_at ASC;")
    todos_age = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM bancos WHERE ativo = 1 ORDER BY padrao DESC, nome ASC;")
    todos_ban = [dict(r) for r in cursor.fetchall() if r["id"] not in bancos_excluidos]
    
    conn.close()
    
    return {
        "status": "synced",
        "orcamentos": todos_orc,
        "catalogos": todos_cat,
        "clientes": todos_cli,
        "agenda": todos_age,
        "bancos": todos_ban,
        "total_orcamentos": len(todos_orc),
        "total_clientes": len(todos_cli),
        "total_agenda": len(todos_age),
        "total_bancos": len(todos_ban)
    }

# Servir Frontend
@app.get("/")
def serve_index():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return {"message": "Frontend index.html não encontrado"}

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
