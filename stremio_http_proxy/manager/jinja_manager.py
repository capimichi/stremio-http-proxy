from jinja2 import Environment, FileSystemLoader
from injector import inject


class JinjaManager:
    @inject
    def __init__(self, template_dir: str):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            cache_size=0,
        )

    def render(self, template_name: str, **context: object) -> str:
        return self.env.get_template(template_name).render(**context)
