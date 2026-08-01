"""Calculator app for Lion-OS."""

from __future__ import annotations

import math

import pygame

from .base import App
from ..widgets import Button, rounded_rect


class CalculatorApp(App):
    name = "Calculator"
    icon = "∑"
    description = "A scientific calculator"
    category = "Utilities"
    default_w = 340
    default_h = 500
    resizable = False

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
            if event.unicode and event.unicode.isprintable():
                ch = event.unicode
                if ch.isdigit() or ch in "+-*/(). ":
                    self.expression += ch
                    self.redraw()
                    return True
                if ch == "=":
                    self._evaluate()
                    return True
            if event.key == pygame.K_BACKSPACE:
                self.expression = self.expression[:-1]
                self.redraw()
                return True
            if event.key == pygame.K_RETURN:
                self._evaluate()
                return True
        return False

    def _btn_rect(self, r, c):
        pad = 6
        bw = (self.rect.width - pad * 6) // 5
        bh = (self.rect.height - 140 - pad * 7) // 6
        x = self.rect.x + pad + c * (bw + pad)
        y = self.rect.y + 110 + pad + r * (bh + pad)
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
            self.expression = ""
        except Exception:
            self.result = "Error"

    def draw(self, surface, rect):
        self.rect = rect
        # display
        disp = pygame.Rect(rect.x + 6, rect.y + 6, rect.width - 12, 96)
        rounded_rect(surface, disp, 10, self.theme.surface_alt)
        font = pygame.font.Font(None, self.os.config.font_size)
        small = pygame.font.Font(None, 18)
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
        font = pygame.font.Font(None, self.os.config.font_size)
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
