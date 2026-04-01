"""Application entry point for the MD Simulation GUI."""

from ui_components import MainWindow


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
