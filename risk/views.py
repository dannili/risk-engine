from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from risk.models import Portfolio, VarRun
from risk.serializers import (
    PortfolioSerializer,
    PositionSerializer,
    VarRunRequestSerializer,
    VarRunSerializer,
)
from risk.services import compute_input_hash


# class PortfolioCreateView(generics.CreateAPIView):
class PortfolioListCreateView(generics.ListCreateAPIView):
    queryset = Portfolio.objects.all()
    serializer_class = PortfolioSerializer


class PositionCreateView(generics.CreateAPIView):
    serializer_class = PositionSerializer

    def perform_create(self, serializer):
        portfolio = get_object_or_404(Portfolio, pk=self.kwargs["portfolio_id"])
        serializer.save(portfolio=portfolio)


class PortfolioVarRunsView(APIView):
    """Submit a VaR run (POST) or list a portfolio's runs (GET)."""

    def get(self, request, portfolio_id):
        portfolio = get_object_or_404(Portfolio, pk=portfolio_id)
        runs = portfolio.var_runs.order_by("-created_at")
        return Response(VarRunSerializer(runs, many=True).data)

    def post(self, request, portfolio_id):
        portfolio = get_object_or_404(Portfolio, pk=portfolio_id)

        request_serializer = VarRunRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.validated_data

        input_hash = compute_input_hash(
            portfolio.id,
            data["method"],
            data["confidence"],
            data["lookback_days"],
            data["as_of_date"],
        )

        existing = VarRun.objects.filter(input_hash=input_hash).first()
        if existing:
            return Response(
                {"run_id": existing.id, "status": existing.status},
                status=status.HTTP_200_OK,
            )

        try:
            with transaction.atomic():
                run = VarRun.objects.create(
                    portfolio=portfolio, input_hash=input_hash, **data
                )
        except IntegrityError:
            # Lost the race to a concurrent identical request; the other
            # request's row is now committed, so fall back to returning it.
            run = VarRun.objects.get(input_hash=input_hash)
            return Response(
                {"run_id": run.id, "status": run.status}, status=status.HTTP_200_OK
            )

        return Response(
            {"run_id": run.id, "status": run.status}, status=status.HTTP_202_ACCEPTED
        )


class VarRunDetailView(generics.RetrieveAPIView):
    queryset = VarRun.objects.all()
    serializer_class = VarRunSerializer
    lookup_url_kwarg = "run_id"
