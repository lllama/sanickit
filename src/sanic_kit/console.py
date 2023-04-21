from rich.text import Text
from textual.app import App
from textual.widgets import Footer, Header, Label, Static


class Logo(Label):
    def render(self):
        return """\
[white on #ea386b]                     
   ▄███ █████ ██     
   ██                
    ▀███████ ███▄    
                ██   
   ████ ████████▀    
                     """


class SanicKit(App):
    CSS = """
    Logo {
        border: heavy red;
        width: 23;
    }
    """

    def compose(self):
        yield Header("Sanic Kit")
        yield Logo()
        yield Footer()
