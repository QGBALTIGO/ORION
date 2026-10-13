from flask import Flask, request, jsonify
import requests
import re
import time
from datetime import datetime

app = Flask("Api homossexual einkkkjj")

app.config['JSON_AS_ASCII'] = False
app.json.compact = False


# ==========================================
# 1. UTILITÁRIOS E TRATADORES ENRIQUECIDOS
# ==========================================
class TextFormatter:
    
    @staticmethod
    def calcular_idade_e_signo(data_nascimento_str: str) -> dict:
        """Calcula a idade exata e o signo com base em formatos dd/mm/yyyy ou yyyy-mm-dd."""
        if not data_nascimento_str:
            return {"idade": None, "signo": None, "maior_de_idade": None}

        data_dt = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                data_dt = datetime.strptime(data_nascimento_str, fmt)
                break
            except ValueError:
                pass

        if not data_dt:
            return {"idade": None, "signo": None, "maior_de_idade": None}

        hoje = datetime.now()
        idade = hoje.year - data_dt.year - ((hoje.month, hoje.day) < (data_dt.month, data_dt.day))

        # Cálculo do Signo
        dia, mes = data_dt.day, data_dt.month
        signos = [
            (1, 20, "Capricórnio"), (2, 19, "Aquário"), (3, 20, "Peixes"),
            (4, 20, "Áries"), (5, 21, "Touro"), (6, 21, "Gêmeos"),
            (7, 23, "Câncer"), (8, 23, "Leão"), (9, 23, "Virgem"),
            (10, 23, "Libra"), (11, 22, "Escorpião"), (12, 22, "Sagitário"),
            (12, 31, "Capricórnio")
        ]
        signo_encontrado = next(signo for m, d, signo in signos if (mes, dia) <= (m, d))

        return {
            "idade": idade,
            "signo": signo_encontrado,
            "maior_de_idade": idade >= 18
        }

    @staticmethod
    def analisar_indicadores_sociais(dados_icmbio: dict) -> dict:
        """
        Analisa a presença de Nome Social ou divergências visando inferir
        uso de nome social / alteração de registro.
        """
        nome_completo = str(dados_icmbio.get("noPessoa") or "").strip()
        nome_social = str(dados_icmbio.get("noSocial") or "").strip() # Caso o ICMBio passe este campo
        sexo_sigla = str(dados_icmbio.get("sgSexo") or "").strip().upper()

        tem_nome_social = bool(nome_social and nome_social.lower() != nome_completo.lower())

        return {
            "possui_nome_social": tem_nome_social,
            "nome_social": nome_social if tem_nome_social else None,
            "observacao_genero": "Possui registro de Nome Social ativo." if tem_nome_social else "Registro civil padrão."
        }

    @staticmethod
    def formatar_sexo(sigla: str) -> dict:
        if not sigla:
            return {"sigla": None, "descricao": "Não informado"}
            
        sigla_limpa = str(sigla).strip().upper()
        mapeamento = {
            "M": "Masculino",
            "F": "Feminino",
            "I": "Intersexo"
        }
        return {
            "sigla": sigla_limpa[:1],
            "descricao": mapeamento.get(sigla_limpa[:1], f"Outro ({sigla})")
        }

    @classmethod
    def formatar_resposta_unica(cls, dados_icmbio: dict, dados_cep: dict, origem_cpf: dict, tempo_inicio: float) -> dict:
        """Monta o JSON unificado e enriquecido."""
        cep_raw = str(dados_icmbio.get("sqCep", ""))
        cep_formatado = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) == 8 else cep_raw

        estados_str = origem_cpf.get("estados_emissao", "")
        lista_estados = [e.strip() for e in estados_str.split(",")] if estados_str != "Desconhecido" else []

        ddd = str(dados_icmbio.get("ddd") or "").strip()
        tel = str(dados_icmbio.get("nuTelefone") or "").strip()
        telefone_completo = f"({ddd}) {tel}" if ddd and tel else None

        nu_endereco = str(dados_icmbio.get("nuEndereco") or "").strip().upper()
        numero_tratado = "S/N" if nu_endereco in ["SN", "S/N", "0", ""] else nu_endereco

        # Processamento de dados extras
        dt_nasc = dados_icmbio.get("dtNascimento")
        info_etaria = cls.calcular_idade_e_signo(dt_nasc)
        info_social = cls.analisar_indicadores_sociais(dados_icmbio)

        return {
            "sucesso": True,
            "metadados": {
                "versao_api": "2.0.0",
                "timestamp": datetime.now().isoformat(),
                "tempo_execucao_ms": round((time.time() - tempo_inicio) * 1000, 2)
            },
            "dados_pessoais": {
                "nome_registro": dados_icmbio.get("noPessoa"),
                "nome_social": info_social["nome_social"],
                "indicadores_sociais": info_social,
                "nome_mae": dados_icmbio.get("noMae"),
                "data_nascimento": dt_nasc,
                "idade": info_etaria["idade"],
                "maior_de_idade": info_etaria["maior_de_idade"],
                "signo": info_etaria["signo"],
                "nacionalidade": "Brasileira" if dados_icmbio.get("nacionalidade") == 1 else "Estrangeira",
                "genero_cadastral": cls.formatar_sexo(dados_icmbio.get("sgSexo")),
                "origem_cpf": {
                    "regiao_fiscal": origem_cpf.get("regiao_fiscal"),
                    "estados_cobertos": lista_estados
                }
            },
            "contato": {
                "telefone": telefone_completo,
                "email": dados_icmbio.get("txEmail") or None
            },
            "endereco": {
                "cep": cep_formatado,
                "logradouro": dados_cep.get("street") or dados_icmbio.get("txEndereco"),
                "numero": numero_tratado,
                "complemento": dados_icmbio.get("txComplemento") or None,
                "bairro": dados_cep.get("neighborhood") or dados_icmbio.get("noBairro"),
                "cidade": dados_cep.get("city"),
                "estado": dados_cep.get("state"),
                "fonte_dados": dados_cep.get("service", "icmbio")
            },
            "auditoria_origem": {
                "icmbio": {
                    "data_integracao": dados_icmbio.get("dtIntegracaoInfoconv"),
                    "codigo_municipio_ibge": dados_icmbio.get("sqMunicipioEndereco"),
                    "logradouro_original": dados_icmbio.get("txEndereco")
                }
            }
        }


# ==========================================
# 2. CLIENTE DE INTEGRAÇÃO (ICMBio)
# ==========================================
class ICMBioClient:
    def __init__(self):
        self.url = "https://sicae.sisicmbio.icmbio.gov.br/principal/infoconv/service-infoconv"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://sicae.sisicmbio.icmbio.gov.br/principal/usuario-externo-pessoa-fisica/create/sqTipoPessoa/1'
        }

    def consultar_cpf(self, cpf_formatado: str) -> dict:
        payload = {'nuCpf': cpf_formatado}
        resposta = requests.post(
            self.url,
            headers=self.headers,
            data=payload,
            timeout=15
        )
        if resposta.status_code != 200:
            raise ConnectionError(f"Erro HTTP {resposta.status_code} na API do ICMBio")
        return resposta.json()


# ==========================================
# 3. SERVIÇOS GEOGRÁFICOS E DE VALIDAÇÃO
# ==========================================
class GeographicService:
    @staticmethod
    def validar_digitos_cpf(cpf: str) -> bool:
        """Valida o cálculo dos dígitos verificadores do CPF."""
        cpf_limpo = re.sub(r'\D', '', cpf)
        if len(cpf_limpo) != 11 or len(set(cpf_limpo)) == 1:
            return False

        for i in range(9, 11):
            soma = sum(int(cpf_limpo[num]) * ((i + 1) - num) for num in range(0, i))
            digito = ((soma * 10) % 11) % 10
            if digito != int(cpf_limpo[i]):
                return False
        return True

    @staticmethod
    def extrair_origem_cpf(cpf: str) -> dict:
        numeros = re.sub(r'\D', '', cpf)
        if len(numeros) != 11:
            return {"regiao_fiscal": None, "estados_emissao": "Desconhecido"}
        
        nono_digito = int(numeros[8])
        regioes = {
            1: "DF, GO, MT, MS, TO",
            2: "AC, AM, AP, PA, RO, RR",
            3: "CE, MA, PI",
            4: "AL, PB, PE, RN",
            5: "BA, SE",
            6: "MG",
            7: "ES, RJ",
            8: "SP",
            9: "PR, SC",
            0: "RS"
        }
        return {
            "regiao_fiscal": nono_digito,
            "estados_emissao": regioes.get(nono_digito, "Desconhecido")
        }

    @staticmethod
    def consultar_brasil_api(cep: str) -> dict:
        if not cep:
            return {}
        cep_limpo = re.sub(r'\D', '', str(cep))
        if len(cep_limpo) != 8:
            return {}
        try:
            r = requests.get(f"https://brasilapi.com.br/api/cep/v1/{cep_limpo}", timeout=3.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}


# ==========================================
# 4. ORQUESTRADOR DA CONSULTA
# ==========================================
class ConsultationEngine:
    def __init__(self):
        self.icmbio = ICMBioClient()

    def normalizar_e_validar_cpf(self, cpf: str) -> str:
        numeros = re.sub(r'\D', '', cpf)
        if len(numeros) != 11:
            raise ValueError("O CPF deve conter exatamente 11 dígitos numéricos.")
        
        if not GeographicService.validar_digitos_cpf(numeros):
            raise ValueError("O número do CPF fornecido é matematicamente inválido.")

        return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"

    def executar(self, cpf_raw: str) -> dict:
        inicio = time.time()
        cpf_formatado = self.normalizar_e_validar_cpf(cpf_raw)
        
        # 1. Consulta ICMBio
        dados_icmbio = self.icmbio.consultar_cpf(cpf_formatado)
        if not dados_icmbio.get("success", False):
            raise FileNotFoundError("CPF não localizado na base de dados do ICMBio.")

        # 2. Busca dados de CEP
        cep_cadastral = str(dados_icmbio.get("sqCep", ""))
        dados_cep = GeographicService.consultar_brasil_api(cep_cadastral) if cep_cadastral else {}

        # 3. Origem do CPF
        origem_cpf = GeographicService.extrair_origem_cpf(cpf_formatado)

        # 4. Retorna a resposta única e tratada
        return TextFormatter.formatar_resposta_unica(dados_icmbio, dados_cep, origem_cpf, inicio)


# ==========================================
# 5. ROTAS DA API
# ==========================================
engine = ConsultationEngine()

@app.route('/consultar', methods=['GET'])
def rota_consultar():
    cpf_raw = request.args.get('cpf')
    
    if not cpf_raw:
        return jsonify({
            "sucesso": False,
            "erro": "O parâmetro 'cpf' é obrigatório."
        }), 400
        
    try:
        resultado = engine.executar(cpf_raw)
        return jsonify(resultado), 200
        
    except ValueError as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 404
    except ConnectionError as e:
        return jsonify({"sucesso": False, "erro": f"Falha de comunicação: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"sucesso": False, "erro": f"Erro interno: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
