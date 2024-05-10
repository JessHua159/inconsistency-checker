from b import B, Y
from c import C

class A(B, C):
    pass

class X(Y):
    pass

print("A.mro: {}".format(A.mro()))