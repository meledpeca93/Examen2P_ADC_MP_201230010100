from django import forms


class OrderForm(forms.Form):
    cliente = forms.CharField(max_length=120, label="Cliente")
    fecha = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        label="Fecha",
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )
    estado = forms.ChoiceField(
        choices=[
            ("Pendiente", "Pendiente"),
            ("Pagada", "Pagada"),
            ("Anulada", "Anulada"),
        ],
        label="Estado",
    )


class DetailForm(forms.Form):
    producto = forms.CharField(max_length=150, label="Producto")
    cantidad = forms.IntegerField(min_value=1, label="Cantidad")
    precio_unitario = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label="Precio unitario",
    )