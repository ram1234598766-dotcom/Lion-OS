"""Calculator app for Lion-OS."""

from __future__ import annotations

import math

import pygame

from .base import App
from ..widgets import Button, cached_font, rounded_rect


class CalculatorApp(App):
    name = "Calculator"
    icon = "∑"
    description = "A scientific calculator"
    category = "Utilities"
    default_w = 340
    default_h = 560
    resizable = False

    # layout constants for the history + display header above the keypad
    HIST_ROWS = 6                 # most recent lines shown, newest on top
    HIST_LINE_H = 16
    HIST_H = HIST_ROWS * HIST_LINE_H + 8
    DISP_H = 66
    TOP_H = HIST_H + 6 + DISP_H + 6

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.expression = ""
        self.result = ""
        self.history = []
        self.buttons = {}
        self._build_buttons()

    def _build_buttons(self):
        b = self.buttons
        rows = [
            ("C", "⌫", "(", ")", "÷"),
            ("7", "8", "9", "×", "√"),
            ("4", "5", "6", "−", "x²"),
            ("1", "2", "3", "+", "%"),
            ("0", ".", "±", "=", "π"),
            ("sin", "cos", "tan", "ln", "log"),
        ]
        for r, row in enumerate(rows):
            for c, label in enumerate(row):
                b[label] = (r, c)

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for label, (r, c) in self.buttons.items():
                btn_rect = self._btn_rect(r, c)
                if btn_rect.collidepoint(local_pos):
                    self._press(label)
                    return True
        if event.type == pygame.KEYDOWN:
            label = self._key_to_label(event)
            if label is not None:
                self._press(label)
                return True
        return False

    def _key_to_label(self, event):
        """Map a KEYDOWN to the matching button label, or None if ignored."""
        ch = getattr(event, "unicode", "") or ""
        if ch:
            if ch in "0123456789.":
                return ch
            if ch in "+-*/()%":
                return ch.replace("*", "×").replace("/", "÷").replace("-", "−")
            if ch == "=":
                return "="
            if ch in "cC":
                return "C"
        if event.key == pygame.K_RETURN:
            return "="
        if event.key == pygame.K_BACKSPACE:
            return "⌫"
        if event.key == pygame.K_ESCAPE:
            return "C"
        return None

    def _font(self, size):
        """Return a pygame font, using os.get_font cache when available."""
        get_font = getattr(self.os, "get_font", None)
        if get_font is not None:
            return get_font(size)
        return cached_font(size)

    def _btn_rect(self, r, c):
        pad = 6
        bw = (self.rect.width - pad * 6) // 5
        top = self.TOP_H
        bh = (self.rect.height - top - 30 - pad * 7) // 6
        x = self.rect.x + pad + c * (bw + pad)
        y = self.rect.y + top + pad + r * (bh + pad)
        return pygame.Rect(x, y, bw, bh)

    def _press(self, label):
        if label == "C":
            self.expression = ""
            self.result = ""
        elif label == "⌫":
            self.expression = self.expression[:-1]
        elif label == "=":
            self._evaluate()
        elif label == "±":
            if self.result:
                self.result = str(-float(self.result))
        elif label == "%":
            self._percent()
        elif label == "π":
            self.expression += "3.14159265"
        elif label == "√":
            self.expression += "sqrt("
        elif label == "x²":
            self.expression += "**2"
        elif label == "sin":
            self.expression += "sin("
        elif label == "cos":
            self.expression += "cos("
        elif label == "tan":
            self.expression += "tan("
        elif label == "ln":
            self.expression += "log("
        elif label == "log":
            self.expression += "log10("
        elif label == "÷":
            self.expression += "/"
        elif label == "×":
            self.expression += "*"
        elif label == "−":
            self.expression += "-"
        else:
            self.expression += label
        self.redraw()

    def _percent(self):
        """Convert the current operand (or last result) to its /100 value."""
        import re

        m = re.search(r"(\d+(?:\.\d+)?|\.\d+)\s*$", self.expression)
        if m:
            start, end = m.span(1)
            val = float(m.group(1)) / 100.0
            if val.is_integer():
                val = int(val)
            else:
                val = round(val, 10)
            self.expression = self.expression[:start] + str(val) + self.expression[end:]
        elif self.result not in ("", "Error"):
            try:
                val = float(self.result) / 100.0
            except (TypeError, ValueError):
                return
            if val.is_integer():
                val = int(val)
            else:
                val = round(val, 10)
            self.result = str(val)

    def _evaluate(self):
        # Security: input is parsed with `ast` (a safe AST walker) instead of
        # eval(). Only numeric literals, the four operators, parentheses,
        # unary +/- and whitelisted math function calls reach the evaluator.
        # No raw input is ever executed.
        import ast

        ALLOWED_FUNCS = {
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
            "tan": math.tan, "log": math.log, "log10": math.log10,
            "abs": abs,
        }

        def _eval_node(node):
            if isinstance(node, ast.Expression):
                return _eval_node(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node, ast.BinOp):
                op = {ast.Add: lambda a, b: a + b,
                      ast.Sub: lambda a, b: a - b,
                      ast.Mult: lambda a, b: a * b,
                      ast.Div: lambda a, b: a / b,
                      ast.Mod: lambda a, b: a % b}.get(type(node.op))
                if op is None:
                    raise ValueError("unsupported operator")
                return op(_eval_node(node.left), _eval_node(node.right))
            if isinstance(node, ast.UnaryOp):
                v = _eval_node(node.operand)
                if isinstance(node.op, ast.USub):
                    return -v
                if isinstance(node.op, ast.UAdd):
                    return v
                raise ValueError("unsupported unary op")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                fn = ALLOWED_FUNCS.get(node.func.id)
                if fn is None:
                    raise ValueError("unsupported function")
                args = [_eval_node(a) for a in node.args]
                if len(args) != 1:
                    raise ValueError("wrong arg count")
                if node.func.id == "log":
                    return math.log(args[0]) if args[0] > 0 else float("nan")
                if node.func.id == "log10":
                    return math.log10(args[0]) if args[0] > 0 else float("nan")
                return fn(*args)
            raise ValueError("unsupported expression")

        try:
            expr = self.expression.replace("^", "**")
            val = _eval_node(ast.parse(expr, mode="eval"))
            if isinstance(val, float):
                if val != val:          # NaN
                    self.result = "Error"
                    return
                if val.is_integer():
                    val = int(val)
                else:
                    val = round(val, 10)
            self.result = str(val)
            self.history.append((self.expression, self.result))
            del self.history[:-30]
            self.expression = ""
        except Exception:
            self.result = "Error"

    def draw(self, surface, rect):
        self.rect = rect
        # history panel: up to ~6 most recent lines, newest on top
        hist = pygame.Rect(rect.x + 6, rect.y + 6, rect.width - 12, self.HIST_H)
        rounded_rect(surface, hist, 10, self.theme.surface)
        hfont = self._font(15)
        recent = list(self.history[-self.HIST_ROWS:][::-1])
        for i, (expr, res) in enumerate(recent):
            line = hfont.render("%s = %s" % (expr, res), True, self.theme.text_dim)
            surface.blit(line, (hist.x + 10, hist.y + 4 + i * self.HIST_LINE_H))
        if not recent:
            img = hfont.render("History", True, self.theme.text_dim)
            surface.blit(img, (hist.x + 10, hist.y + 4))
        # display: current expression + result
        disp = pygame.Rect(rect.x + 6, hist.bottom + 6, rect.width - 12, self.DISP_H)
        rounded_rect(surface, disp, 10, self.theme.surface_alt)
        font = self._font(self.os.config.font_size)
        small = self._font(18)
        expr_img = small.render(self.expression or "0", True, self.theme.text_dim)
        surface.blit(expr_img, (disp.x + 12, disp.y + 10))
        res_img = font.render(self.result or "0", True, self.theme.accent)
        surface.blit(res_img, (disp.right - res_img.get_width() - 12, disp.bottom - res_img.get_height() - 8))

        rows = [
            ("C", "⌫", "(", ")", "÷"),
            ("7", "8", "9", "×", "√"),
            ("4", "5", "6", "−", "x²"),
            ("1", "2", "3", "+", "%"),
            ("0", ".", "±", "=", "π"),
            ("sin", "cos", "tan", "ln", "log"),
        ]
        font = self._font(self.os.config.font_size)
        for r, row in enumerate(rows):
            for c, label in enumerate(row):
                btn_rect = self._btn_rect(r, c)
                is_op = label in "=÷×−+()√x²%"
                is_fn = label in ("sin", "cos", "tan", "ln", "log")
                if label == "C":
                    color = self.theme.danger
                elif label == "=":
                    color = self.theme.accent
                elif is_op or is_fn:
                    color = self.theme.surface_alt
                else:
                    color = self.theme.surface
                if btn_rect.collidepoint(pygame.mouse.get_pos()):
                    color = self.theme.active if len(self.theme.active) == 3 else self.theme.active[:3]
                rounded_rect(surface, btn_rect, 8, color)
                img = font.render(label, True, self.theme.text)
                surface.blit(img, img.get_rect(center=btn_rect.center))
