"""
Backend REST API & Banco de Dados Centralizado - Marmoraria SaaS Multi-Tenant
Arquitetura Database-per-Tenant com isolamento total por subdomínio
"""
import os
import re
import json
import shutil
import sqlite3
import hashlib
import secrets
from datetime import datetime
from typing import List, Optional, Any, Dict
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Body, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

def hash_password(password: str) -> str:
    """Hash SHA-256 seguro com salt embutido"""
    salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}:{h}"

def verify_password(password: str, hashed: str) -> bool:
    """Verifica senha contra hash salt:hash"""
    if not hashed or ":" not in hashed:
        return False
    salt, original_hash = hashed.split(":", 1)
    test_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return secrets.compare_digest(test_hash, original_hash)

app = FastAPI(
    title="Marmoraria SaaS Multi-Tenant API",
    description="API centralizada em nuvem com isolamento completo de banco de dados por marmoraria",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caminho dos bancos de dados e arquivos estáticos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
TENANTS_DIR = os.path.join(DATA_DIR, "tenants")
os.makedirs(TENANTS_DIR, exist_ok=True)

MASTER_DB_PATH = os.path.join(DATA_DIR, "master.db")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
INDEX_PATH = os.path.join(FRONTEND_DIR, "index.html")
if not os.path.exists(INDEX_PATH):
    INDEX_PATH = os.path.join(BASE_DIR, "index.html")

ADMIN_PATH = os.path.join(FRONTEND_DIR, "admin.html")
if not os.path.exists(ADMIN_PATH):
    ADMIN_PATH = os.path.join(BASE_DIR, "admin.html")

# ContextVar para isolamento concorrente por requisição
current_tenant_var: ContextVar[str] = ContextVar("current_tenant", default="marmobraz")

def get_master_db():
    conn = sqlite3.connect(MASTER_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_master_db():
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
        chave TEXT PRIMARY KEY,
        valor TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Inicializa Senha Mestre do SuperAdmin se não existir
    cursor.execute("SELECT valor FROM config WHERE chave = 'admin_password_hash';")
    if not cursor.fetchone():
        agora = datetime.now().isoformat()
        # Senha inicial padrão: admin123 (pode ser trocada na tela)
        h = hash_password("admin123")
        cursor.execute("INSERT INTO config (chave, valor, updated_at) VALUES ('admin_password_hash', ?, ?);", (h, agora))
        cursor.execute("INSERT OR IGNORE INTO config (chave, valor, updated_at) VALUES ('primeiro_acesso', '1', ?);", (agora,))

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        telefone TEXT,
        documento TEXT,
        email TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    # Tenant padrão inicial
    cursor.execute("SELECT COUNT(*) as total FROM tenants;")
    if cursor.fetchone()["total"] == 0:
        agora = datetime.now().isoformat()
        cursor.execute("""
        INSERT INTO tenants (id, name, telefone, documento, email, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, ("marmobraz", "Marmoraria Marmobraz", "(11) 99999-9999", "", "contato@marmobraz.com.br", "active", agora, agora))
    conn.commit()
    conn.close()

def extract_subdomain(host: str) -> str:
    if not host:
        return "marmobraz"
    host = host.split(":")[0].lower()
    parts = host.split(".")
    # Reconhece subdomínio em mnservice.net.br
    if len(parts) >= 3 and parts[-2] == "mnservice" and parts[-1] == "net.br":
        return parts[0]
    # Reconhece subdomínio genérico
    if len(parts) >= 2 and parts[0] not in ("www", "mnservice", "localhost", "127", "179"):
        return parts[0]
    return "marmobraz"

def get_tenant_db_path(tenant_id: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]", "", tenant_id).lower()
    if not clean or clean in ("admin", "master", "www"):
        clean = "marmobraz"
    
    db_file = os.path.join(TENANTS_DIR, f"{clean}.db")
    # Migração automática do banco legado para o tenant marmobraz
    legacy_db = os.path.join(DATA_DIR, "marmoraria.db")
    if clean == "marmobraz" and not os.path.exists(db_file) and os.path.exists(legacy_db):
        shutil.copy2(legacy_db, db_file)
        
    return db_file

def init_tenant_db_schema(conn, tenant_name: str = "Marmoraria"):
    cursor = conn.cursor()
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS catalogos (
        tipo TEXT PRIMARY KEY,
        dados_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agenda (
        id TEXT PRIMARY KEY,
        orcamento_id TEXT,
        cliente_nome TEXT NOT NULL,
        cliente_fone TEXT,
        endereco TEXT,
        tipo TEXT NOT NULL,
        data TEXT NOT NULL,
        turno TEXT DEFAULT 'comercial',
        responsavel TEXT,
        status TEXT DEFAULT 'agendado',
        observacoes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

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

    cursor.execute("SELECT COUNT(*) as total FROM bancos;")
    if cursor.fetchone()["total"] == 0:
        agora = datetime.now().isoformat()
        cursor.executemany("""
        INSERT INTO bancos (id, nome, tipo, agencia, conta, titular, cor, saldo_inicial, padrao, ativo, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [
            ("banco_itau", "Banco Itaú PJ", "corrente", "1234", "56789-0", f"{tenant_name} Ltda", "#f97316", 0.0, 1, 1, agora, agora),
            ("banco_sicoob", "Sicoob Cooperativa", "corrente", "3040", "12890-1", f"{tenant_name} Ltda", "#0284c7", 0.0, 0, 1, agora, agora),
            ("banco_caixa_fisico", "Caixa Físico / Gaveta", "carteira_fisica", "-", "-", f"Balcão {tenant_name}", "#10b981", 0.0, 0, 1, agora, agora)
        ])

    # Tabela de Usuários & Equipe (Autenticação e Permissões do Tenant)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha_hash TEXT NOT NULL,
        cargo TEXT DEFAULT 'Administrador',
        telefone TEXT,
        ativo INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Seed inicial de usuário admin para a marmoraria se estiver vazio
    cursor.execute("SELECT COUNT(*) as total FROM usuarios;")
    if cursor.fetchone()["total"] == 0:
        agora = datetime.now().isoformat()
        u_id = f"usr_{secrets.token_hex(6)}"
        u_email = f"admin@{re.sub(r'[^a-zA-Z0-9]', '', tenant_name).lower() or 'marmoraria'}.com.br"
        # Senha padrão inicial para a marmoraria: 123456
        u_hash = hash_password("123456")
        cursor.execute("""
        INSERT INTO usuarios (id, nome, email, senha_hash, cargo, telefone, ativo, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (u_id, f"Admin {tenant_name}", u_email, u_hash, "Administrador", "", 1, agora, agora))

    conn.commit()

def get_db(tenant_id: Optional[str] = None):
    if not tenant_id:
        tenant_id = current_tenant_var.get()
    path = get_tenant_db_path(tenant_id)
    is_new = not os.path.exists(path)
    
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    
    if is_new:
        company_name = tenant_id.capitalize()
        try:
            mconn = get_master_db()
            mcur = mconn.cursor()
            mcur.execute("SELECT name FROM tenants WHERE id = ?;", (tenant_id,))
            row = mcur.fetchone()
            if row:
                company_name = row["name"]
            mconn.close()
        except Exception:
            pass
        init_tenant_db_schema(conn, company_name)
        
    return conn

# Inicializa banco mestre
init_master_db()

# Middleware de Injeção de Tenant
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    host = request.headers.get("host", "")
    subdomain = extract_subdomain(host)

    # Permite override via query param (ex: ?tenant=pedrasnobres) para testes/visualização
    param_tenant = request.query_params.get("tenant")
    if param_tenant:
        subdomain = param_tenant.strip().lower()

    # Permite override via cabeçalho para testes ou chamadas de API
    header_tenant = request.headers.get("x-tenant-id")
    if header_tenant:
        subdomain = header_tenant.strip().lower()

    token = current_tenant_var.set(subdomain)
    try:
        response = await call_next(request)
        response.headers["X-Tenant-ID"] = subdomain
        return response
    finally:
        current_tenant_var.reset(token)


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

# --- MODELOS PYDANTIC PARA AUTENTICAÇÃO & USUÁRIOS ---

class AdminLoginRequest(BaseModel):
    senha: str

class AdminChangePasswordRequest(BaseModel):
    senha_atual: str
    nova_senha: str

class TenantCreateRequest(BaseModel):
    id: str
    name: str
    telefone: Optional[str] = ""
    documento: Optional[str] = ""
    email: Optional[str] = ""
    status: Optional[str] = "active"
    admin_nome: Optional[str] = ""
    admin_email: Optional[str] = ""
    admin_senha: Optional[str] = ""

class TenantStatusRequest(BaseModel):
    status: str

class TenantLoginRequest(BaseModel):
    email: str
    senha: str

class UsuarioCreateRequest(BaseModel):
    nome: str
    email: str
    senha: str
    cargo: Optional[str] = "Administrador"
    telefone: Optional[str] = ""

class UsuarioUpdateRequest(BaseModel):
    nome: str
    email: str
    cargo: Optional[str] = "Administrador"
    telefone: Optional[str] = ""
    senha: Optional[str] = None
    ativo: Optional[int] = 1

# --- ROTAS DE AUTENTICAÇÃO DO SUPERADMIN ---

@app.post("/api/admin/login")
def admin_login(payload: AdminLoginRequest):
    """Autentica o SuperAdmin Master"""
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE chave = 'admin_password_hash';")
    row = cursor.fetchone()
    
    cursor.execute("SELECT valor FROM config WHERE chave = 'primeiro_acesso';")
    pa_row = cursor.fetchone()
    primeiro_acesso = (pa_row and pa_row["valor"] == "1")
    conn.close()

    if not row or not verify_password(payload.senha, row["valor"]):
        raise HTTPException(status_code=401, detail="Senha mestre incorreta.")

    token = secrets.token_hex(24)
    # Guarda token na master config (válido para sessão)
    agora = datetime.now().isoformat()
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (chave, valor, updated_at) VALUES ('session_token', ?, ?);", (token, agora))
    conn.commit()
    conn.close()

    return {
        "status": "authenticated",
        "token": token,
        "primeiro_acesso": bool(primeiro_acesso),
        "message": "Login realizado com sucesso."
    }

@app.post("/api/admin/change-password")
def admin_change_password(payload: AdminChangePasswordRequest, x_admin_token: Optional[str] = Header(None)):
    """Altera a Senha Mestre do SuperAdmin"""
    conn = get_master_db()
    cursor = conn.cursor()
    
    # Valida senha atual
    cursor.execute("SELECT valor FROM config WHERE chave = 'admin_password_hash';")
    row = cursor.fetchone()
    if not row or not verify_password(payload.senha_atual, row["valor"]):
        conn.close()
        raise HTTPException(status_code=400, detail="A senha atual está incorreta.")

    if not payload.nova_senha or len(payload.nova_senha) < 6:
        conn.close()
        raise HTTPException(status_code=400, detail="A nova senha deve ter no mínimo 6 caracteres.")

    novo_hash = hash_password(payload.nova_senha)
    agora = datetime.now().isoformat()
    cursor.execute("UPDATE config SET valor = ?, updated_at = ? WHERE chave = 'admin_password_hash';", (novo_hash, agora))
    cursor.execute("UPDATE config SET valor = '0', updated_at = ? WHERE chave = 'primeiro_acesso';", (agora,))
    conn.commit()
    conn.close()

    return {"status": "success", "message": "Senha mestre atualizada com sucesso!"}

def verificar_autenticacao_admin(request: Request):
    """Verifica se a requisição ao SuperAdmin possui o token correto"""
    token_cliente = request.headers.get("x-admin-token") or request.query_params.get("token")
    if not token_cliente:
        raise HTTPException(status_code=401, detail="Acesso não autorizado ao SuperAdmin.")
        
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE chave = 'session_token';")
    row = cursor.fetchone()
    conn.close()
    
    if not row or row["valor"] != token_cliente:
        raise HTTPException(status_code=401, detail="Sessão do SuperAdmin expirada ou inválida.")

# --- ROTAS DE GESTÃO DE TENANTS (SUPERADMIN) ---

@app.get("/api/tenant/info")
def get_tenant_info():
    """Retorna dados da marmoraria conectada nesta URL/subdomínio"""
    tenant_id = current_tenant_var.get()
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tenants WHERE id = ?;", (tenant_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {
            "id": tenant_id,
            "name": f"Marmoraria {tenant_id.capitalize()}",
            "status": "active",
            "registered": False
        }
    
    return {
        "id": row["id"],
        "name": row["name"],
        "telefone": row["telefone"],
        "documento": row["documento"],
        "email": row["email"],
        "status": row["status"],
        "registered": True
    }

@app.get("/api/admin/tenants")
def list_tenants(request: Request):
    """Lista todas as marmorarias e métricas de banco"""
    verificar_autenticacao_admin(request)
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tenants ORDER BY created_at DESC;")
    tenants = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    for t in tenants:
        t_id = t["id"]
        db_path = get_tenant_db_path(t_id)
        size_kb = round(os.path.getsize(db_path) / 1024, 1) if os.path.exists(db_path) else 0
        total_orc = 0
        total_usr = 0
        
        if os.path.exists(db_path):
            try:
                tconn = sqlite3.connect(db_path, timeout=5.0)
                tconn.row_factory = sqlite3.Row
                tcur = tconn.cursor()
                tcur.execute("SELECT COUNT(*) as total FROM orcamentos;")
                total_orc = tcur.fetchone()["total"]
                tcur.execute("SELECT COUNT(*) as total FROM usuarios;")
                total_usr = tcur.fetchone()["total"]
                tconn.close()
            except Exception:
                pass
                
        t["db_size_kb"] = size_kb
        t["total_orcamentos"] = total_orc
        t["total_usuarios"] = total_usr
        
    return tenants

@app.post("/api/admin/tenants")
def create_tenant(payload: TenantCreateRequest, request: Request):
    """Cria uma nova marmoraria, banco isolado e usuário administrador inicial"""
    verificar_autenticacao_admin(request)
    slug = re.sub(r"[^a-zA-Z0-9_-]", "", payload.id).lower()
    if not slug or len(slug) < 2:
        raise HTTPException(status_code=400, detail="Subdomínio inválido. Use apenas letras e números.")
        
    if slug in ("admin", "master", "api", "www"):
        raise HTTPException(status_code=400, detail="Este subdomínio é reservado do sistema.")
        
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tenants WHERE id = ?;", (slug,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Já existe uma marmoraria cadastrada com este subdomínio.")
        
    agora = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO tenants (id, name, telefone, documento, email, status, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        slug,
        payload.name,
        payload.telefone or "",
        payload.documento or "",
        payload.email or "",
        payload.status or "active",
        agora,
        agora
    ))
    conn.commit()
    conn.close()
    
    # Inicializa o banco de dados isolado da nova marmoraria
    tconn = get_db(slug)
    tcursor = tconn.cursor()

    # Se foram passados dados do usuário admin personalizado
    admin_email = payload.admin_email or payload.email or f"admin@{slug}.com.br"
    admin_nome = payload.admin_nome or f"Admin {payload.name}"
    admin_senha = payload.admin_senha or "123456"

    # Atualiza ou insere o admin inicial configurado
    tcursor.execute("SELECT id FROM usuarios WHERE email = ?;", (admin_email,))
    if not tcursor.fetchone():
        u_id = f"usr_{secrets.token_hex(6)}"
        u_hash = hash_password(admin_senha)
        tcursor.execute("""
        INSERT INTO usuarios (id, nome, email, senha_hash, cargo, telefone, ativo, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'Administrador', ?, 1, ?, ?);
        """, (u_id, admin_nome, admin_email, u_hash, payload.telefone or "", agora, agora))
        tconn.commit()
    
    tconn.close()
    
    return {
        "status": "created",
        "id": slug,
        "name": payload.name,
        "url": f"https://{slug}.mnservice.net.br",
        "admin_email": admin_email
    }

@app.put("/api/admin/tenants/{tenant_id}/status")
def update_tenant_status(tenant_id: str, payload: TenantStatusRequest, request: Request):
    """Bloqueia ou libera acesso de uma marmoraria"""
    verificar_autenticacao_admin(request)
    conn = get_master_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tenants SET status = ?, updated_at = ? WHERE id = ?;", (
        payload.status,
        datetime.now().isoformat(),
        tenant_id
    ))
    conn.commit()
    conn.close()
    return {"status": "updated", "id": tenant_id, "new_status": payload.status}

@app.get("/api/admin/tenants/{tenant_id}/backup")
def backup_tenant_db(tenant_id: str, request: Request):
    """Download do banco SQLite completo do cliente"""
    verificar_autenticacao_admin(request)
    db_path = get_tenant_db_path(tenant_id)
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Banco de dados da marmoraria não encontrado.")
    return FileResponse(db_path, filename=f"backup_{tenant_id}.db", media_type="application/x-sqlite3")

# --- ROTAS DE AUTENTICAÇÃO E USUÁRIOS DO TENANT (CLIENTE) ---

@app.post("/api/auth/login")
def tenant_login(payload: TenantLoginRequest):
    """Login de colaboradores no tenant da URL ativa"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?;", (payload.email.strip().lower(),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    if not user["ativo"]:
        raise HTTPException(status_code=403, detail="Este usuário está desativado na empresa.")

    if not verify_password(payload.senha, user["senha_hash"]):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    token = secrets.token_hex(24)
    return {
        "status": "authenticated",
        "token": token,
        "usuario": {
            "id": user["id"],
            "nome": user["nome"],
            "email": user["email"],
            "cargo": user["cargo"] or "Administrador",
            "telefone": user["telefone"] or ""
        }
    }

@app.get("/api/usuarios")
def list_usuarios():
    """Lista todos os colaboradores do tenant ativo"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, email, cargo, telefone, ativo, created_at, updated_at FROM usuarios ORDER BY nome ASC;")
    users = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return users

@app.post("/api/usuarios")
def create_usuario(payload: UsuarioCreateRequest):
    """Cadastra um novo colaborador no tenant ativo"""
    email_limpo = payload.email.strip().lower()
    if not email_limpo or not payload.nome:
        raise HTTPException(status_code=400, detail="Nome e e-mail são obrigatórios.")

    if not payload.senha or len(payload.senha) < 4:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 4 caracteres.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE email = ?;", (email_limpo,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Já existe um colaborador cadastrado com este e-mail.")

    agora = datetime.now().isoformat()
    u_id = f"usr_{secrets.token_hex(6)}"
    u_hash = hash_password(payload.senha)

    cursor.execute("""
    INSERT INTO usuarios (id, nome, email, senha_hash, cargo, telefone, ativo, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?);
    """, (u_id, payload.nome.strip(), email_limpo, u_hash, payload.cargo or "Administrador", payload.telefone or "", agora, agora))
    conn.commit()
    conn.close()

    return {"status": "created", "id": u_id, "nome": payload.nome, "email": email_limpo}

@app.put("/api/usuarios/{usuario_id}")
def update_usuario(usuario_id: str, payload: UsuarioUpdateRequest):
    """Atualiza dados, cargo ou senha de um colaborador"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?;", (usuario_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    agora = datetime.now().isoformat()
    if payload.senha and len(payload.senha) >= 4:
        u_hash = hash_password(payload.senha)
        cursor.execute("""
        UPDATE usuarios 
        SET nome = ?, email = ?, cargo = ?, telefone = ?, senha_hash = ?, ativo = ?, updated_at = ?
        WHERE id = ?;
        """, (payload.nome.strip(), payload.email.strip().lower(), payload.cargo, payload.telefone or "", u_hash, payload.ativo, agora, usuario_id))
    else:
        cursor.execute("""
        UPDATE usuarios 
        SET nome = ?, email = ?, cargo = ?, telefone = ?, ativo = ?, updated_at = ?
        WHERE id = ?;
        """, (payload.nome.strip(), payload.email.strip().lower(), payload.cargo, payload.telefone or "", payload.ativo, agora, usuario_id))

    conn.commit()
    conn.close()
    return {"status": "updated", "id": usuario_id}

@app.delete("/api/usuarios/{usuario_id}")
def delete_usuario(usuario_id: str):
    """Exclui um colaborador do tenant"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM usuarios WHERE ativo = 1;")
    if cursor.fetchone()["total"] <= 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Não é possível excluir o único usuário da empresa.")

    cursor.execute("DELETE FROM usuarios WHERE id = ?;", (usuario_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": usuario_id}

# --- ROTAS DE SERVIÇO DE FRONTEND ---

@app.get("/admin")
def serve_admin():
    """Painel SuperAdmin"""
    if os.path.exists(ADMIN_PATH):
        return FileResponse(ADMIN_PATH)
    return {"message": "Admin admin.html não encontrado"}

@app.get("/")
def serve_index(request: Request):
    """Serve a aplicação para o cliente ou admin dependendo do subdomínio"""
    host = request.headers.get("host", "")
    sub = extract_subdomain(host)
    
    # Se o subdomínio for admin, exibe o painel de controle
    if sub == "admin" and os.path.exists(ADMIN_PATH):
        return FileResponse(ADMIN_PATH)
        
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return {"message": "Frontend index.html não encontrado"}

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


