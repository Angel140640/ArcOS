"""Cadastro de aplicativos: código numérico -> pacote Android."""

import re

from .config import read_json, write_json

PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
ACT_RE = re.compile(r"^[A-Za-z0-9_.$/]+$")
ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{0,19}$")


class AppDB:
    def __init__(self):
        data = read_json("apps.json", {"apps": []})
        raw = data.get("apps", []) if isinstance(data, dict) else []
        self.apps = [
            a for a in raw
            if isinstance(a, dict) and isinstance(a.get("code"), int) and a.get("package") and a.get("name")
        ]

    def save(self):
        write_json("apps.json", {"apps": sorted(self.apps, key=lambda a: a["code"])})

    def all(self):
        return sorted(self.apps, key=lambda a: a["code"])

    def next_code(self):
        used = {a["code"] for a in self.apps}
        n = 1
        while n in used:
            n += 1
        return n

    def find(self, ref):
        """Resolve '02', '2', um alias, o nome ou o pacote."""
        ref = ref.strip()
        if ref.isdigit():
            n = int(ref)
            for a in self.apps:
                if a["code"] == n:
                    return a
            return None
        low = ref.lower()
        for a in self.apps:
            if a.get("alias") == low:
                return a
        for a in self.apps:
            if a["name"].lower() == low or a["package"].lower() == low:
                return a
        return None

    def search(self, query):
        q = query.strip().lower()
        return [
            a for a in self.all()
            if q in a["name"].lower() or q in a["package"].lower() or q in (a.get("alias") or "")
        ]

    def _check_alias(self, alias, ignore_code=None):
        alias = alias.strip().lower()
        if not ALIAS_RE.match(alias):
            raise ValueError("Alias inválido: use letras minúsculas, números, - ou _ (começando com letra, até 20)")
        for a in self.apps:
            if a.get("alias") == alias and a["code"] != ignore_code:
                raise ValueError("O alias '%s' já é usado pelo código %02d" % (alias, a["code"]))
        return alias

    def add(self, package, name=None, activity=None, alias=None):
        package = package.strip()
        if not PKG_RE.match(package):
            raise ValueError("Pacote inválido. Exemplo: com.discord")
        for a in self.apps:
            if a["package"] == package:
                raise ValueError("%s já está cadastrado (código %02d)" % (package, a["code"]))
        if activity and not ACT_RE.match(activity):
            raise ValueError("Activity inválida")
        alias = self._check_alias(alias) if alias else None
        name = re.sub(r"[\x00-\x1f\x7f]", "", (name or package.split(".")[-1].capitalize())).strip()[:40]
        if not name:
            raise ValueError("Nome vazio")
        app = {"code": self.next_code(), "name": name, "package": package}
        if activity:
            app["activity"] = activity
        if alias:
            app["alias"] = alias
        self.apps.append(app)
        self.save()
        return app

    def remove(self, code):
        before = len(self.apps)
        self.apps = [a for a in self.apps if a["code"] != code]
        if len(self.apps) != before:
            self.save()
            return True
        return False

    def set_alias(self, code, alias):
        app = self.find(str(code))
        if not app:
            raise ValueError("Código não encontrado")
        if alias is None:
            app.pop("alias", None)
        else:
            app["alias"] = self._check_alias(alias, ignore_code=code)
        self.save()
        return app
