"""Route poles analysis: cables of a routes KMZ crossed with the BDGD poles.

routes   reads the cables of the KMZ/KML
city     finds the city boundary (IBGE)
pole_base downloads and reads the utilities' pole bases
engine   measures the cables, their overlap and the poles near them
kmz      writes the result KMZ files
"""
