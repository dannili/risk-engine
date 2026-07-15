from django.urls import path

from risk import views

urlpatterns = [
    path("portfolios/", views.PortfolioCreateView.as_view()),
    path(
        "portfolios/<int:portfolio_id>/positions/",
        views.PositionCreateView.as_view(),
    ),
    path(
        "portfolios/<int:portfolio_id>/var-runs/",
        views.PortfolioVarRunsView.as_view(),
    ),
    path("var-runs/<int:run_id>/", views.VarRunDetailView.as_view()),
]
