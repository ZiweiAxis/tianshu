# Matrix 全局状态

_matrix_client = None


def get_matrix_client():
    return _matrix_client


def set_matrix_client(client):
    global _matrix_client
    _matrix_client = client
