"""Signal controllers. Importing a module registers the controllers it defines."""
from teamb.controllers.base import REGISTRY, Controller, available, make_controller, register  # noqa: F401
from teamb.controllers import fixed_time  # noqa: F401
