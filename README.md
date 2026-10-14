# 🪨 Sistema SaaS de Gestão e Orçamentos - Marmoraria Marmobraz

> Sistema moderno, ágil e intuitivo para cálculo de orçamentos, emissão de propostas comerciais formais (A4), ordens de corte e produção para fábrica e gestão de múltiplos orçamentos.  
> Baseado nas fórmulas reais e regras da planilha de movimentação de caixa e orçamentos da **Marmoraria Marmobraz** (`3-Mov.Caixa 2024.xlsx`).

---

## 🌐 Acesso Online na Nuvem (Railway)
* **URL do Sistema no Ar:** [https://marmoraria-saas-production.up.railway.app](https://marmoraria-saas-production.up.railway.app)
* **Projeto no Railway:** **MN** (`https://railway.com/project/8fdf85af-2af9-4748-8a91-e06518edcb79`)
* **Serviço:** `marmoraria-saas`
* **Status:** 🟢 Online / Produção

---

## 📂 Localização do Projeto no Computador
* **Diretório do Projeto:** `C:\Users\sistema_03\.gemini\antigravity\scratch\marmoraria-saas`
* **Atalho de Trabalho (Desktop):** `C:\Users\sistema_03\Desktop\Calculadora_Marmoraria.html`
* **Atalho Nuvem (Desktop):** `C:\Users\sistema_03\Desktop\ACESSAR_SISTEMA_MARMORARIA_NUVEM.url`

---

## 🚀 Como Executar / Atualizar

### 🌟 Opção 1: Acesso Online (Em Qualquer Computador / Celular)
Abra diretamente o link:  
👉 **[https://marmoraria-saas-production.up.railway.app](https://marmoraria-saas-production.up.railway.app)**

### 💻 Opção 2: Atualizar Alterações no Railway
Dê dois cliques no script:  
👉 **`ATUALIZAR_SISTEMA_NO_RAILWAY.bat`**  
Ele envia automaticamente o código atualizado para a nuvem.

### 💻 Opção 3: Executar Localmente
Dê dois cliques no arquivo **`ABRIR_SISTEMA.bat`** ou diretamente no arquivo **`index.html`**.

---

## 🎯 Principais Módulos & Recursos

### 1. 🧮 Calculadora Técnica & Motor de Orçamento
- **Cálculo de Área de Chapa (m²):** $(Comp \times Larg) \times Qtd + RB$.
- **Configurador Automático de Rodabanca (Espelho) e Saia:**
  - Seleção dos lados com parede: Fundo, 2 Lados (L), 3 Lados (U), Perímetro Completo.
  - Seleção de lados da Saia 45°: Frente, L, 3 Lados ou Ilha.
  - Alturas configuráveis (4cm, 7cm, 10cm, 15cm, 20cm, etc.).
  - Conversão linear para acréscimo exato de m² de chapa.
- **Acabamentos Lineares Paramétricos:**
  - Fórmulas de lados com acabamento: $1C$, $1C + 1L$, $1C + 2L$, $2C$, perímetro, etc.
  - Tipos de acabamento (Meia-Esquadria 45°, Boleado Simples, Meio-Boleado, Bisotê, Polimento Reto, Peito de Pombo).
  - Cálculo instantâneo do valor de mão de obra linear ($R\$/m$).
- **Cubas e Acessórios:**
  - Modelos de Inox Tramontina (Nº 1, Nº 2, Gourmet), Louças Deca/Incepa, Cubas Esculpidas com rampa oculta ou fundo falso removível, Tanques.
  - Preço padrão de catálogo + campo editável para personalização rápida.

### 2. 📋 Emissão de Proposta Comercial A4
- Timbrado profissional da **Marmoraria Marmobraz** com CNPJ, endereço e telefones.
- Dados completos do cliente, local da entrega, prazo de validade e vendedor.
- Tabela detalhada de peças com medidas, materiais, acréscimos técnicos, acabamentos e cubas.
- Condições de pagamento à vista com desconto e simulação de parcelamento.
- Termos de garantia de fabricação e montagem com campos para assinaturas.
- Botão direto para **Imprimir / Salvar em PDF** formatado para folha A4.
- Botão para **Copiar Resumo Formatado para o WhatsApp** com emojis e formatação profissional.

### 3. 🏭 Ficha de Produção & Ordem de Corte da Fábrica
- Ordem técnica baseada no modelo `F Entregar` da planilha de controle.
- **Sem valores financeiros (R$)**, focada exclusivamente na execução da marcenaria/marmoraria.
- Tarja de destaque visual gigante no topo: **`[ 🚚 ENTREGAR E MONTAR NA OBRA ]`** ou **`[ 🏪 VEM PEGAR NA FÁBRICA ]`**.
- Medidas de corte bruto ($C \times L$), detalhes milimétricos de rodabanca e saia, tipo de acabamento linear e recorte de cuba.
- Checklist de bancada para serrador e acabador: `[ ] Corte`, `[ ] Colagem`, `[ ] Polido`.
- Canhoto destacável de entrega com declaração de recebimento para o cliente assinar na obra.

### 4. 📁 Histórico & Gestão de Múltiplos Orçamentos
- Salvar e carregar múltiplos orçamentos no navegador com persistência (`localStorage`).
- Filtros por status: *Em Aberto*, *Aprovado*, *Em Produção*, *Concluído* e *Recusado*.
- Busca dinâmica em tempo real por nome do cliente, número do orçamento ou telefone.
- Duplicação rápida de propostas para orçamentos alternativos.

### 5. 🪨 Catálogos Dinâmicos com CRUD Completo
- **Pedras & Chapas:** Cadastro, edição, pesquisa, ajuste rápido de preço por $m²$, exclusão e restauração padrão.
- **Cubas & Acessórios:** Cadastro, edição de tipos e modelos, ajuste rápido de preço em R$, exclusão e restauração.
- **Tipos de Acabamento Linear:** Gestão de nomes e valores por metro linear.
- **Fórmulas de Lados:** Gestão e criação de novas fórmulas de contorno de acabamento.

---

## 🏗️ Estrutura de Diretórios

```
marmoraria-saas/
├── ABRIR_SISTEMA.bat              # Script inicializador de clique duplo
├── README.md                      # Documentação completa do sistema
├── index.html                     # Aplicação web desktop responsiva e completa
├── frontend/
│   └── index.html                 # Cópia para servir no servidor web
└── backend/                       # Estrutura preparada para Etapa 4 (API REST / PostgreSQL)
    ├── app.py
    └── requirements.txt
```

---

## 🔒 Persistência de Dados Híbrida & Nuvem (Tempo Real)
O sistema opera em modelo híbrido **Cloud-First com Offline-First Resiliente**:
- **Banco de Dados Centralizado (Nuvem):** SQLite Relacional com modo WAL (`/app/data/marmoraria.db`) servido por FastAPI no Railway.
- **Armazenamento Local do Navegador (`localStorage`):** Garante funcionamento instantâneo sem travamentos na digitação e operação offline.
- **Sincronização Bidirecional Automática (`/api/sync`):**
  - Sincroniza ao abrir o sistema, a cada 30 segundos em segundo plano e ao focar na janela.
  - Qualquer orçamento criado ou alterado pelo vendedor no computador reflete imediatamente na tela da fábrica ou no celular.
- **Catálogos em Nuvem:** Chapas/Pedras, Cubas, Acabamentos lineares, Fórmulas de Lados e Modalidades de Logística centralizados.
