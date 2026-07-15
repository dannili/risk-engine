from rest_framework import serializers

from risk.models import Portfolio, Position, VarResult, VarRun


class PortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Portfolio
        fields = ["id", "name", "base_currency", "created_at"]
        read_only_fields = ["id", "created_at"]


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ["id", "ticker", "quantity"]
        read_only_fields = ["id"]


class VarRunRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarRun
        fields = ["method", "confidence", "lookback_days", "as_of_date"]


class VarResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarResult
        fields = [
            "var_value",
            "expected_shortfall",
            "breach_count",
            "kupiec_pvalue",
            "computed_at",
        ]


class VarRunSerializer(serializers.ModelSerializer):
    run_id = serializers.IntegerField(source="id", read_only=True)
    result = serializers.SerializerMethodField()

    class Meta:
        model = VarRun
        fields = [
            "run_id",
            "portfolio_id",
            "method",
            "confidence",
            "lookback_days",
            "as_of_date",
            "status",
            "created_at",
            "completed_at",
            "result",
        ]

    def get_result(self, obj):
        result = obj.results.first()
        return VarResultSerializer(result).data if result else None
