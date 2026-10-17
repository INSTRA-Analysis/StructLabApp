"""Element-load directions the FEF code cannot represent are rejected, not misread."""

import pytest

from core.load import ElementLoad, LoadDirection, LoadType
from solver.fem_loads import fixed_end_forces


def _udl(direction: LoadDirection) -> ElementLoad:
    return ElementLoad(element_id=7, load_type=LoadType.UDL, magnitude=1000.0,
                       direction=direction)


@pytest.mark.parametrize("direction", [LoadDirection.GLOBAL_X, LoadDirection.GLOBAL_Y,
                                       LoadDirection.GLOBAL_Z])
@pytest.mark.parametrize("is_3d", [False, True])
def test_global_directions_are_rejected(direction, is_3d):
    with pytest.raises(ValueError, match="element 7"):
        fixed_end_forces(_udl(direction), 4.0, is_3d=is_3d)


def test_local_z_is_rejected_in_2d_but_fine_in_3d():
    with pytest.raises(ValueError, match="LOCAL_Z"):
        fixed_end_forces(_udl(LoadDirection.LOCAL_Z), 4.0, is_3d=False)
    f = fixed_end_forces(_udl(LoadDirection.LOCAL_Z), 4.0, is_3d=True)
    assert f[2] == pytest.approx(1000.0 * 4.0 / 2)      # V_z at end i


def test_local_y_unchanged():
    f2 = fixed_end_forces(_udl(LoadDirection.LOCAL_Y), 4.0)
    f3 = fixed_end_forces(_udl(LoadDirection.LOCAL_Y), 4.0, is_3d=True)
    assert f2[1] == pytest.approx(2000.0) and f3[1] == pytest.approx(2000.0)
