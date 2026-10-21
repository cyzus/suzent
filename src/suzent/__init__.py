"""Suzent.

LiteLLM decides its verbosity when it is imported, from ``LITELLM_LOG``. It
was being set in ``agent_manager``, which several modules that import LiteLLM
directly are loaded before -- so on those paths the setting arrived too late
and LiteLLM logged at DEBUG, putting every request it made, prompts included,
into the service log the console displays. Setting it in the package's own
``__init__`` puts it before any import of LiteLLM that goes through Suzent.

LiteLLM also downloads its model price table from raw.githubusercontent.com
on import, which behind the mainland China firewall stalls startup until the
request times out. There it uses the copy bundled with the package instead.
"""

import os

from suzent import network_region

os.environ.setdefault("LITELLM_LOG", "ERROR")
if network_region.china_mode():
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
