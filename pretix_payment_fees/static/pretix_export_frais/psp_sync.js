/**
 * Script pour la page de synchronisation PSP
 * Gère l'indicateur de chargement lors de la soumission du formulaire
 */
document.addEventListener('DOMContentLoaded', function() {
    // Trouver le formulaire et le bouton
    var form = document.querySelector('form[method="post"]');
    var button = document.getElementById('sync-button');

    if (form && button) {
        // Intercepter la soumission du formulaire
        form.addEventListener('submit', function(e) {
            // Ne pas empêcher la soumission, juste modifier le bouton
            button.disabled = true;
            button.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Synchronisation en cours...';

            // S'assurer que le formulaire est bien soumis
            return true;
        });
    }
});