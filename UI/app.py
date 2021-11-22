from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from Bot.bot import Bot


class MainGrid(GridLayout):
    def __init__(self, **kwargs):
        super(MainGrid, self).__init__(**kwargs)
        self.cols = 2
        self.rows = 3
        self.size_hint_y = None
        self.height = 30
        self.bot = Bot()

        # Inner grid for navigation menu
        self.navbarGrid = GridLayout()
        self.navbarGrid.cols = 8
        self.navbarGrid.rows = 1

        self.homeBtn = Button(text="Home", font_size=15)
        self.startBtn = Button(text="Start Bot", font_size=15)
        self.startBtn.bind(on_press=self.startBot)
        self.stopBtn = Button(text="Stop Bot", font_size=15)
        self.botStatusLbl = Label(text="Bot Status: ")
        self.botStatus = Label(text="")
        self.marketStatusLbl = Label(text="Market Status: ")
        self.marketStatus = Label(text="")

        self.navbarGrid.add_widget(self.homeBtn)
        self.navbarGrid.add_widget(self.startBtn)
        self.navbarGrid.add_widget(self.stopBtn)
        self.navbarGrid.add_widget(self.botStatusLbl)
        self.navbarGrid.add_widget(self.botStatus)
        self.navbarGrid.add_widget(self.marketStatusLbl)
        self.navbarGrid.add_widget(self.marketStatus)

        self.add_widget(self.navbarGrid)

    def startBot(self):
        self.bot.start_bot()
        # pass


class BotUI(App):
    def build(self):
        return MainGrid()


if __name__ == '__main__':
    BotUI().run()
