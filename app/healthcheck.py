import sys
from app.services.redis_store import health


def main():
    component = sys.argv[1] if len(sys.argv) > 1 else 'worker'
    data = health(component)
    if not data or not data.get('ok', True):
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == '__main__':
    main()
