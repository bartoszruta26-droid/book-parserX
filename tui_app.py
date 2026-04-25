#!/usr/bin/env python3
"""
Terminal User Interface (TUI) Application
A simple interactive TUI with menu navigation and basic functionality.
"""

import curses
import time
from datetime import datetime


class TUIApp:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.menu_items = [
            "📊 Dashboard",
            "📁 File Manager",
            "⚙️  Settings",
            "ℹ️  About",
            "🚪 Exit"
        ]
        self.current_index = 0
        self.running = True
        self.status_message = "Welcome! Use ↑↓ to navigate, Enter to select"
        
        # Initialize colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected item
        curses.init_pair(2, curses.COLOR_CYAN, -1)                   # Header
        curses.init_pair(3, curses.COLOR_GREEN, -1)                  # Status
        curses.init_pair(4, curses.COLOR_YELLOW, -1)                 # Content
        
    def draw_header(self):
        """Draw the application header"""
        height, width = self.stdscr.getmaxyx()
        title = "╔══════════════════════════════════════════════════════════╗"
        app_name = "║           🖥️  TERMINAL USER INTERFACE 🖥️                ║"
        separator = "╠══════════════════════════════════════════════════════════╣"
        
        try:
            self.stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
            self.stdscr.addstr(0, 0, title[:width-1])
            self.stdscr.addstr(1, 0, app_name[:width-1])
            self.stdscr.addstr(2, 0, separator[:width-1])
            self.stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
        except curses.error:
            pass
    
    def draw_menu(self):
        """Draw the main menu"""
        height, width = self.stdscr.getmaxyx()
        start_y = 4
        
        for i, item in enumerate(self.menu_items):
            y = start_y + i
            if y >= height - 3:
                break
            
            try:
                if i == self.current_index:
                    self.stdscr.attron(curses.color_pair(1))
                    line = f"  ▶ {item} ".ljust(width - 1)
                    self.stdscr.addstr(y, 0, line[:width-1])
                    self.stdscr.attroff(curses.color_pair(1))
                else:
                    line = f"    {item} ".ljust(width - 1)
                    self.stdscr.addstr(y, 0, line[:width-1])
            except curses.error:
                pass
    
    def draw_content(self):
        """Draw content area based on selection"""
        height, width = self.stdscr.getmaxyx()
        content_start = 10
        
        content_lines = []
        
        if self.current_index == 0:  # Dashboard
            content_lines = [
                "┌─────────────────────────────────────────────────────┐",
                "│  📊 DASHBOARD                                       │",
                "├─────────────────────────────────────────────────────┤",
                f"│  Current Time: {datetime.now().strftime('%H:%M:%S')}                          │",
                f"│  Date: {datetime.now().strftime('%Y-%m-%d')}                              │",
                "│                                                     │",
                "│  System Status: ● Online                           │",
                "│  Active Users: 1                                   │",
                "│  Memory Usage: 45%                                 │",
                "└─────────────────────────────────────────────────────┘"
            ]
        elif self.current_index == 1:  # File Manager
            content_lines = [
                "┌─────────────────────────────────────────────────────┐",
                "│  📁 FILE MANAGER                                    │",
                "├─────────────────────────────────────────────────────┤",
                "│  /workspace/                                        │",
                "│  ├── chunk_script.sh                                │",
                "│  ├── convert_to_txt.sh                              │",
                "│  ├── README.md                                      │",
                "│  ├── LICENSE                                        │",
                "│  └── tui_app.py ← current                           │",
                "└─────────────────────────────────────────────────────┘"
            ]
        elif self.current_index == 2:  # Settings
            content_lines = [
                "┌─────────────────────────────────────────────────────┐",
                "│  ⚙️  SETTINGS                                       │",
                "├─────────────────────────────────────────────────────┤",
                "│  [✓] Enable color support                           │",
                "│  [✓] Show status bar                                │",
                "│  [ ] Debug mode                                     │",
                "│  [✓] Auto-refresh                                   │",
                "│                                                     │",
                "│  Press 't' to toggle items                          │",
                "└─────────────────────────────────────────────────────┘"
            ]
        elif self.current_index == 3:  # About
            content_lines = [
                "┌─────────────────────────────────────────────────────┐",
                "│  ℹ️  ABOUT                                          │",
                "├─────────────────────────────────────────────────────┤",
                "│  Terminal User Interface Demo                       │",
                "│  Version: 1.0.0                                     │",
                "│                                                     │",
                "│  Features:                                          │",
                "│  • Keyboard navigation                              │",
                "│  • Color support                                    │",
                "│  • Dynamic content display                          │",
                "│  • Status messages                                  │",
                "│                                                     │",
                "│  Built with Python curses                           │",
                "└─────────────────────────────────────────────────────┘"
            ]
        
        for i, line in enumerate(content_lines):
            y = content_start + i
            if y >= height - 3:
                break
            try:
                self.stdscr.attron(curses.color_pair(4))
                self.stdscr.addstr(y, 0, line[:width-1])
                self.stdscr.attroff(curses.color_pair(4))
            except curses.error:
                pass
    
    def draw_status_bar(self):
        """Draw the status bar at the bottom"""
        height, width = self.stdscr.getmaxyx()
        try:
            self.stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
            status_line = f" {self.status_message} ".ljust(width - 1)
            self.stdscr.addstr(height - 1, 0, status_line[:width-1])
            self.stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)
        except curses.error:
            pass
    
    def draw(self):
        """Draw the entire interface"""
        self.stdscr.clear()
        self.draw_header()
        self.draw_menu()
        self.draw_content()
        self.draw_status_bar()
        self.stdscr.refresh()
    
    def handle_input(self):
        """Handle keyboard input"""
        key = self.stdscr.getch()
        
        if key == ord('q') or key == ord('Q'):
            self.running = False
        elif key == curses.KEY_UP or key == ord('k'):
            self.current_index = (self.current_index - 1) % len(self.menu_items)
            self.status_message = "Use ↑↓ to navigate, Enter to select"
        elif key == curses.KEY_DOWN or key == ord('j'):
            self.current_index = (self.current_index + 1) % len(self.menu_items)
            self.status_message = "Use ↑↓ to navigate, Enter to select"
        elif key == curses.KEY_ENTER or key == 10 or key == 13:
            if self.current_index == len(self.menu_items) - 1:  # Exit
                self.running = False
            else:
                self.status_message = f"Selected: {self.menu_items[self.current_index]}"
        elif key == ord('t'):
            self.status_message = "Toggle action triggered!"
        elif key == ord('r'):
            self.status_message = "Refreshed at " + datetime.now().strftime('%H:%M:%S')
        elif key == ord('h'):
            self.status_message = "Help: ↑↓ navigate, Enter select, q quit, r refresh"
    
    def run(self):
        """Main application loop"""
        # Hide cursor
        curses.curs_set(0)
        
        while self.running:
            self.draw()
            self.handle_input()


def main(stdscr):
    """Entry point for the TUI application"""
    app = TUIApp(stdscr)
    app.run()


if __name__ == "__main__":
    print("Starting Terminal User Interface...")
    print("Controls:")
    print("  ↑/↓ or k/j : Navigate menu")
    print("  Enter      : Select item")
    print("  q          : Quit")
    print("  r          : Refresh")
    print("  h          : Help")
    print("\nPress Enter to start...")
    input()
    
    curses.wrapper(main)
