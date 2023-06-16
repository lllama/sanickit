from sanic import Sanic

app = Sanic.get_app()


@app.before_server_start
async def before_server_start(app, _):
    ...


@app.after_server_start
async def after_server_start(app, _):
    ...


@app.after_server_stop
async def after_server_stop(app, _):
    ...
