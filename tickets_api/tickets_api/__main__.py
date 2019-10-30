"""
Trying a new pattern from
https://moshez.wordpress.com/2016/06/07/__name__-__main__-considered-harmful/
"""
if __name__ != '__main__':
        raise ImportError("This module cannot be imported.")
from tickets_api.tickets_api import serve  # noqa (prevent pycodestyle throwing E402)
serve.main()
