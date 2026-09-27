"""Evaluate only path assignments, never import or initialize the application."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[1] / 'main.py'
PATHS = {
    'DB_PATH': 'data/kangboacademy.db',
    'FRONTEND_DIR': 'frontend',
    'COURSES_DIR': 'frontend/courses',
    'BOOK_COURSES_HTML': 'frontend/book-courses.html',
    'KNOWLEDGE_GRAPH_JSON': 'data/knowledge-graph.json',
    'SHOP_PRODUCTS_JSON': 'data/shop-products.json',
}


class ProjectRootTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding='utf-8')
        self.tree = ast.parse(self.source)

    def evaluate_paths(self, environment):
        names = {'PROJECT_ROOT', *PATHS}
        nodes = [node for node in self.tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
        self.assertEqual(len(nodes), len(names))
        lookups = []

        def getenv(key, default=None):
            lookups.append(key)
            return environment.get(key, default)

        scope = {'Path': Path, 'os': SimpleNamespace(getenv=getenv)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)
        self.assertEqual(lookups, ['KANGBO_PROJECT_ROOT'])
        self.assertIsInstance(scope['DB_PATH'], str)
        return scope

    def test_production_defaults_unchanged(self):
        scope = self.evaluate_paths({})
        for name, relative in PATHS.items():
            self.assertEqual(Path(scope[name]), Path('/var/www/kangboacademy') / relative)

    def test_all_six_paths_follow_isolated_root(self):
        root = '/tmp/kangbo-test-only/project with spaces'
        scope = self.evaluate_paths({'KANGBO_PROJECT_ROOT': root})
        for name, relative in PATHS.items():
            self.assertEqual(Path(scope[name]), Path(root) / relative)
            self.assertNotIn('/var/www/', str(scope[name]))

    def test_root_setting_is_not_exposed_by_functions(self):
        for function in self.tree.body:
            if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(function):
                    if isinstance(node, ast.Name):
                        self.assertNotEqual(node.id, 'PROJECT_ROOT')
                    if isinstance(node, ast.Constant):
                        self.assertNotEqual(node.value, 'KANGBO_PROJECT_ROOT')

    def test_main_compiles_without_execution(self):
        compile(self.source, str(SOURCE), 'exec')


if __name__ == '__main__':
    unittest.main()
