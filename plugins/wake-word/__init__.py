"""Wake word: start a voice call by saying a phrase, spotted on this machine."""

from suzent.plugins import PluginContext

from . import routes


def register(ctx: PluginContext) -> None:
    ctx.register_route("status", routes.status)
    ctx.register_route("model", routes.install_model, methods=("POST",))
    ctx.register_websocket("listen", routes.listen)
