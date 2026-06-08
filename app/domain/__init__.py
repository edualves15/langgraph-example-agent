"""Domínios de negócio (plugues). Cada subpacote expõe um `DOMAIN: Domain`.

O engine genérico (`app/agent/`) é agnóstico daqui; o composition root (`app/main.py`)
escolhe qual domínio montar. Ver `app/agent/domain.py`.
"""
