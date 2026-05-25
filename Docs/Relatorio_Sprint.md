# 📄 Relatório Técnico: EcoTrack - Sprint IA & IoT

**Disciplina:** Disruptive Architectures: IOT, IOB & Generative IA  
**Projeto:** EcoTrack - Sustentabilidade e Saúde na Palma da Mão  

---

## 👥 Integrantes do Grupo
* **RM560685** - Gustavo Dantas
* **RM560262** - Paulo Neto
* **RM559906** - Davi Vasconcelos Souza

---

## 1. Visão Geral da Solução
O **EcoTrack** é uma plataforma desenvolvida para resolver uma dor latente do consumidor moderno: a dificuldade de interpretar rótulos nutricionais e ambientais. Utilizando uma combinação de IoT (leitura de produtos) e IA Generativa, o sistema traduz dados técnicos complexos em recomendações personalizadas, promovendo escolhas conscientes e sustentáveis.

## 2. O Problema de IA
Consumidores frequentemente ignoram informações vitais (como presença de microplásticos na embalagem ou excesso de sódio) por não compreenderem a linguagem técnica dos rótulos. O problema que resolvemos é a **tradução contextualizada de dados estruturados para o perfil de comportamento do usuário (IoB)**.

## 3. Arquitetura da Inteligência Artificial
### 3.1 Modelo Utilizado
* **Modelo:** LLM (Large Language Model) - IA Generativa.
* **Justificativa:** Diferente de modelos de classificação binária, o LLM permite cruzar variáveis heterogêneas (objetivos de saúde, restrições alérgicas e dados ambientais) para gerar uma resposta natural e persuasiva, capaz de sugerir alternativas em vez de apenas apontar erros.

### 3.2 Estratégia de Dados
* **Origem:** Dados extraídos do banco de dados global *Open Food Facts* e perfis de usuário armazenados em **Oracle Database**.
* **Formato:** JSON estruturado contendo metadados do produto e preferências do usuário.
* **Volume:** O sistema é alimentado por uma base de centenas de milhares de produtos, garantindo alta disponibilidade de informação para a IA.

## 4. Fluxo de Funcionamento
1. **Captura:** O usuário busca um produto no aplicativo.
2. **Integração:** O backend busca os dados do produto e o histórico/perfil do usuário no Banco de Dados.
3. **Prompting:** Um JSON consolidado é enviado para a API de IA Generativa.
4. **Insight:** A IA analisa as discrepâncias (ex: "Produto rico em açúcar vs Usuário quer reduzir açúcar") e gera um relatório.
5. **Entrega:** O usuário recebe o alerta e uma sugestão de produto alternativo mais sustentável.

## 5. Demonstração Técnica
O protótipo funcional foi desenvolvido em **Streamlit (Python)**, demonstrando em tempo real a capacidade da IA de interpretar o banco de dados de produtos e reagir a diferentes perfis de comportamento (Vegano, Intolerante a Glúten, etc).

## Como rodar
No terminal, navegue até a pasta onde está o app.py e utilize o comando abaixo:

```bash
streamlit run app.py
```

---
