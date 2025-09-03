"""Configurações de teste compartilhadas."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importa primeiro o módulo de testes de autenticação para que o patch de
# ``requests`` seja aplicado antes de o cliente real ser importado.
from tests import test_auth_3cplus as auth_tests  # type: ignore

import auth_3cplus as auth_module

# Garante que o cliente principal utilize a mesma classe Timeout
# utilizada pelos testes.
auth_module.Timeout = auth_tests.Timeout
