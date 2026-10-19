"""Route poles analysis: cables of a routes KMZ crossed with the BDGD poles.

Pure computation, no database and no FastAPI. The entry points are in
pipeline: run_analysis (routes inside one city) and run_backbone (one analysis
per city the routes pass through).

routes      reads the cables of the KMZ/KML
city        finds the city boundaries (IBGE)
city_poles  the poles inside each city, from every utility base
pole_base   downloads and reads the utilities' pole bases
clip        cuts the cables at a city border
engine      measures the cables, their overlap and the poles near them
kmz         writes the result KMZ files
pipeline    chains the steps above into the data to store
"""
